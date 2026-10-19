"""
PUAF 不确定性可视化工具包 (utils/puaf_vis.py)

在训练流程中调用，自动提取 UGAF 的 uI/uP/M_I/M_P 并生成热力图。
用法：在 base_model.py 的 validation_step 中调用 maybe_visualize_puaf()。

配置（yaml 中添加）：
  train_params:
    puaf_vis:
      enabled: true
      vis_interval: 10        # 每隔多少 epoch 可视化一次
      max_frames: 8           # 每次可视化最多保存多少帧
      scale_idx: -1           # 使用第几层融合尺度 (-1 = 最后一层)
      top_percentile: 95      # 用于候选帧筛选的分位数
      out_dir: "vis_puaf"     # 输出子目录（相对于 logger 日志目录）
      gauss_sigma: 5.0        # 高斯扩散半径（像素）
      paper_mode: false       # 是否同时输出论文级图片 + .npz 原始数据
      overlay_alpha: 0.55     # 热力图叠加透明度

离线论文出图（训练结束后）：
  python tools/compose_paper_figure.py \\
      --npz_dir vis_puaf/epoch_50 \\
      --scenes 001234 003456 \\
      --out paper_fig_uncertainty.pdf
"""

import os
import numpy as np
import torch
import torch.nn as nn

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# =====================================================================
# 1. UGAF 插桩 —— monkey-patch forward 使其缓存 uncertainty dict
# =====================================================================

def instrument_ugaf_modules(model: nn.Module):
    """
    遍历模型中的 UGAF (PointUGAF) 模块，替换 forward 使其始终缓存
    _last_uncertainty 字典，后续可直接读取。
    返回 [(scale_idx, ugaf_module), ...] 列表。
    """
    fusion = getattr(model, "fusion", None)
    if fusion is None:
        return []
    fusion_modules = getattr(fusion, "fusion_modules", None)
    if fusion_modules is None:
        return []

    instrumented = []
    for idx, adapter in enumerate(fusion_modules):
        ugaf = getattr(adapter, "ugaf", None)
        if ugaf is None:
            continue
        if getattr(ugaf, "_puaf_vis_instrumented", False):
            instrumented.append((idx, ugaf))
            continue

        # 保存原始 forward
        _orig_forward = ugaf.forward

        def _make_wrapper(orig_fn):
            def wrapped_forward(self_ugaf, x1, x2, return_uncertainty=False):
                import torch as _torch
                import torch.nn.functional as _F

                u_img_a = self_ugaf.uncertainty_img(x1)
                u_pts_a = self_ugaf.uncertainty_pts(x2)

                if self_ugaf.enable_epistemic and (self_ugaf.training or self_ugaf.epistemic_in_eval):
                    u_img_e = self_ugaf._mc_epistemic(self_ugaf.uncertainty_img, x1)
                    u_pts_e = self_ugaf._mc_epistemic(self_ugaf.uncertainty_pts, x2)
                    u_img = u_img_a + self_ugaf.lambda_e * u_img_e
                    u_pts = u_pts_a + self_ugaf.lambda_e * u_pts_e
                else:
                    u_img_e = u_pts_e = None
                    u_img = u_img_a
                    u_pts = u_pts_a

                confidence_mask = _F.softmax(_torch.cat([-u_img, -u_pts], dim=1), dim=1)
                m_img = confidence_mask[:, 0:1]
                m_pts = confidence_mask[:, 1:2]

                x_fuse = m_img * x1 + m_pts * x2
                x_fuse_conv = self_ugaf.conv(x_fuse)
                point_weight = self_ugaf.point_attn(x_fuse_conv)
                x_out = x_fuse_conv * point_weight

                self_ugaf._last_uncertainty = {
                    "u_img_aleatoric": u_img_a,
                    "u_pts_aleatoric": u_pts_a,
                    "u_img_epistemic": u_img_e,
                    "u_pts_epistemic": u_pts_e,
                    "u_img": u_img,
                    "u_pts": u_pts,
                    "M_img": m_img,
                    "M_pts": m_pts,
                }

                if return_uncertainty:
                    return x_out, self_ugaf._last_uncertainty
                return x_out
            return wrapped_forward

        ugaf.forward = _make_wrapper(_orig_forward).__get__(ugaf, type(ugaf))
        ugaf._puaf_vis_instrumented = True
        instrumented.append((idx, ugaf))

    return instrumented


# =====================================================================
# 2. 栅格化 —— 把逐点值画到图像网格（高斯扩散填充稀疏区域）
# =====================================================================

def rasterize_to_image(img_indices: np.ndarray, values: np.ndarray,
                       h: int, w: int, sigma: float = 5.0) -> np.ndarray:
    """
    将 (N,) values 按 img_indices (N,2) [row,col] 栅格化到 (H,W)，
    并用高斯扩散填充稀疏区域，使热力图连续可读。

    Args:
        img_indices: (N, 2) [row, col]
        values: (N,)
        h, w: 图像尺寸
        sigma: 高斯扩散半径（像素），越大越平滑
    Returns:
        (H, W) float32，无投影覆盖区域为 NaN
    """
    from scipy.ndimage import gaussian_filter

    acc = np.zeros((h, w), dtype=np.float64)
    cnt = np.zeros((h, w), dtype=np.float64)

    rows = img_indices[:, 0].astype(np.int64)
    cols = img_indices[:, 1].astype(np.int64)
    valid = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    rows, cols = rows[valid], cols[valid]
    vals = values[valid].astype(np.float64)

    np.add.at(acc, (rows, cols), vals)
    np.add.at(cnt, (rows, cols), 1.0)

    # 高斯扩散：对累加值和计数分别做平滑，再求比值
    acc_smooth = gaussian_filter(acc, sigma=sigma)
    cnt_smooth = gaussian_filter(cnt, sigma=sigma)

    out = np.full((h, w), np.nan, dtype=np.float32)
    # 只在有足够扩散覆盖的区域填值（阈值为峰值计数的 1%）
    threshold = max(cnt_smooth.max() * 0.01, 1e-8)
    valid_mask = cnt_smooth > threshold
    out[valid_mask] = (acc_smooth[valid_mask] / cnt_smooth[valid_mask]).astype(np.float32)
    return out


def denorm_image(img_chw: torch.Tensor, img_shape_hw, normalizer):
    """将归一化的 (C,H,W) 图像还原为 (H,W,3) float [0,1]。"""
    h, w = int(img_shape_hw[0]), int(img_shape_hw[1])
    arr = img_chw.detach().cpu().numpy()[:3, :h, :w].transpose(1, 2, 0)
    if normalizer is not None and len(normalizer) == 2:
        mean = np.asarray(normalizer[0], dtype=np.float32)
        std = np.asarray(normalizer[1], dtype=np.float32)
        arr = arr * std + mean
    return np.clip(arr, 0.0, 1.0)


# =====================================================================
# 3. 绘图
# =====================================================================

def _overlay_heatmap(ax, rgb, heatmap, cmap, title, fig, vmin=None, vmax=None, alpha=0.55):
    """在 RGB 上叠加半透明热力图。"""
    ax.imshow(rgb)
    mask = ~np.isnan(heatmap)
    if mask.any():
        display = np.ma.array(heatmap, mask=~mask)
        im = ax.imshow(display, cmap=cmap, alpha=alpha, vmin=vmin, vmax=vmax)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title(title, fontsize=11)
    ax.axis("off")


def draw_uncertainty_figure(rgb, map_ui, map_up, map_mi, map_mp,
                            ui_vals, up_vals, mi_vals, mp_vals,
                            title: str, subtitle: str, out_path: str):
    """
    画 2×4 面板，热力图半透明叠加在 RGB 上：
    Row1: RGB | uI overlay | uP overlay | (uP-uI) overlay
    Row2: M_I overlay | M_P overlay | hist | stats
    """
    if not HAS_MPL:
        return

    fig, axes = plt.subplots(2, 4, figsize=(22, 11), dpi=150)
    fig.suptitle(title, fontsize=15, fontweight='bold')

    # --- Row 1 ---
    axes[0, 0].imshow(rgb)
    axes[0, 0].set_title("RGB", fontsize=11)
    axes[0, 0].axis("off")

    # 计算 uI/uP 共享色域
    all_u = np.concatenate([ui_vals, up_vals])
    if all_u.size == 0:
        plt.close(fig)
        return
    u_vmin, u_vmax = np.percentile(all_u, 2), np.percentile(all_u, 98)

    _overlay_heatmap(axes[0, 1], rgb, map_ui, "inferno",
                     "uI (image uncert.)", fig, vmin=u_vmin, vmax=u_vmax)
    _overlay_heatmap(axes[0, 2], rgb, map_up, "inferno",
                     "uP (point uncert.)", fig, vmin=u_vmin, vmax=u_vmax)

    diff = map_up - map_ui
    d_abs = np.nanmax(np.abs(diff[~np.isnan(diff)])) if np.any(~np.isnan(diff)) else 1.0
    _overlay_heatmap(axes[0, 3], rgb, diff, "coolwarm",
                     "uP − uI", fig, vmin=-d_abs, vmax=d_abs)

    # --- Row 2 ---
    _overlay_heatmap(axes[1, 0], rgb, map_mi, "viridis",
                     "M_I (img weight)", fig, vmin=0, vmax=1)
    _overlay_heatmap(axes[1, 1], rgb, map_mp, "viridis",
                     "M_P (pts weight)", fig, vmin=0, vmax=1)

    # 直方图
    axes[1, 2].hist(mi_vals, bins=50, alpha=0.7, label="M_I", color="tab:blue", edgecolor="white", linewidth=0.3)
    axes[1, 2].hist(mp_vals, bins=50, alpha=0.6, label="M_P", color="tab:orange", edgecolor="white", linewidth=0.3)
    axes[1, 2].set_title("M_I / M_P distribution", fontsize=11)
    axes[1, 2].set_xlabel("weight value")
    axes[1, 2].set_ylabel("count")
    axes[1, 2].legend(loc="upper center", fontsize=9)

    # 统计面板
    axes[1, 3].axis("off")
    stats_text = (
        f"uI  mean = {np.nanmean(ui_vals):+.4f}\n"
        f"uP  mean = {np.nanmean(up_vals):+.4f}\n"
        f"uI  p95  = {np.percentile(ui_vals, 95):+.4f}\n"
        f"uP  p95  = {np.percentile(up_vals, 95):+.4f}\n"
        f"────────────────\n"
        f"M_I mean = {np.nanmean(mi_vals):.4f}\n"
        f"M_P mean = {np.nanmean(mp_vals):.4f}\n"
        f"M_I > 0.5 = {(mi_vals > 0.5).mean()*100:.1f}%\n"
        f"M_P > 0.5 = {(mp_vals > 0.5).mean()*100:.1f}%"
    )
    axes[1, 3].text(0.08, 0.55, stats_text, fontsize=11, verticalalignment="center",
                    fontfamily="monospace", transform=axes[1, 3].transAxes,
                    bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8))
    axes[1, 3].set_title("Statistics", fontsize=11)

    fig.text(0.5, 0.005, subtitle, ha="center", fontsize=8, color="gray")
    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


# =====================================================================
# 3b. 论文级绘图 —— 干净、紧凑、高分辨率
# =====================================================================

# 论文字体配置（IEEE / Springer / CVPR 通用）
_PAPER_RC = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 9,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "mathtext.fontset": "stix",
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
}


def _paper_overlay(ax, rgb, heatmap, cmap, label, fig, vmin=None, vmax=None,
                   alpha=0.6, show_colorbar=True):
    """论文版热力图叠加，更紧凑的 colorbar。"""
    ax.imshow(rgb)
    mask = ~np.isnan(heatmap)
    if mask.any():
        display = np.ma.array(heatmap, mask=~mask)
        im = ax.imshow(display, cmap=cmap, alpha=alpha, vmin=vmin, vmax=vmax,
                       interpolation="bilinear")
        if show_colorbar:
            cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, aspect=30)
            cb.ax.tick_params(labelsize=6)
    ax.set_title(label, fontsize=9, pad=3)
    ax.axis("off")


def draw_paper_figure(rgb, map_ui, map_up, map_mi, map_mp,
                      ui_vals, up_vals, out_path: str,
                      alpha: float = 0.6,
                      col_width_inch: float = 3.4,
                      scene_label: str = ""):
    """
    输出适合论文的单场景 1×5 行条图：
      (a) RGB | (b) u_I | (c) u_P | (d) M_I | (e) M_P

    - 300 DPI、serif 字体、紧凑布局
    - 同时输出 PDF 和 PNG 两种格式
    - uI/uP 共享色域、M_I/M_P 共享 [0,1] 色域

    Args:
        col_width_inch: 论文单栏宽度 (IEEE 双栏≈3.4", 单栏≈7")
    """
    if not HAS_MPL:
        return

    with plt.rc_context(_PAPER_RC):
        h_img, w_img = rgb.shape[:2]
        aspect = h_img / max(w_img, 1)
        n_cols = 5
        panel_w = col_width_inch * 2 / n_cols  # 用双栏宽度
        panel_h = panel_w * aspect
        fig, axes = plt.subplots(1, n_cols, figsize=(panel_w * n_cols + 0.6, panel_h + 0.35))

        # (a) RGB
        axes[0].imshow(rgb)
        axes[0].set_title("(a) Input Image", fontsize=9, pad=3)
        axes[0].axis("off")

        # uI/uP 共享色域
        all_u = np.concatenate([ui_vals, up_vals])
        if all_u.size == 0:
            plt.close(fig)
            return
        u_vmin, u_vmax = np.percentile(all_u, 1), np.percentile(all_u, 99)

        # (b) uI
        _paper_overlay(axes[1], rgb, map_ui, "inferno",
                       r"(b) $\sigma_I$ (image)", fig,
                       vmin=u_vmin, vmax=u_vmax, alpha=alpha)

        # (c) uP
        _paper_overlay(axes[2], rgb, map_up, "inferno",
                       r"(c) $\sigma_P$ (point)", fig,
                       vmin=u_vmin, vmax=u_vmax, alpha=alpha)

        # (d) M_I
        _paper_overlay(axes[3], rgb, map_mi, "viridis",
                       r"(d) $M_I$", fig,
                       vmin=0, vmax=1, alpha=alpha)

        # (e) M_P
        _paper_overlay(axes[4], rgb, map_mp, "viridis",
                       r"(e) $M_P$", fig,
                       vmin=0, vmax=1, alpha=alpha)

        if scene_label:
            fig.text(0.01, 0.01, scene_label, fontsize=7, color="gray",
                     fontstyle="italic")

        fig.tight_layout(pad=0.3, w_pad=0.4)

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        # 同时保存 PDF (矢量) 和 PNG (位图)
        base, _ = os.path.splitext(out_path)
        fig.savefig(base + ".pdf", format="pdf")
        fig.savefig(base + ".png", format="png")
        plt.close(fig)


def draw_paper_comparison(scene_list, out_path: str,
                          alpha: float = 0.6,
                          total_width_inch: float = 7.0):
    """
    多场景对比图（适合论文 Figure），N×5 网格：
    每行一个场景: (a) RGB | (b) u_I | (c) u_P | (d) M_I | (e) M_P

    Args:
        scene_list: list of dicts, 每个 dict 含:
            rgb, map_ui, map_up, map_mi, map_mp, ui_vals, up_vals, label
        out_path: 输出路径（自动生成 .pdf 和 .png）
        total_width_inch: 总图宽 (IEEE 双栏≈7.16")
    """
    if not HAS_MPL or len(scene_list) == 0:
        return

    with plt.rc_context(_PAPER_RC):
        n_rows = len(scene_list)
        n_cols = 5
        # 计算所有场景共享的色域
        all_ui = np.concatenate([s["ui_vals"] for s in scene_list])
        all_up = np.concatenate([s["up_vals"] for s in scene_list])
        all_u = np.concatenate([all_ui, all_up])
        if all_u.size == 0:
            return
        u_vmin, u_vmax = np.percentile(all_u, 1), np.percentile(all_u, 99)

        # 根据第一个场景的宽高比算面板尺寸
        h0, w0 = scene_list[0]["rgb"].shape[:2]
        aspect = h0 / max(w0, 1)
        panel_w = total_width_inch / n_cols
        panel_h = panel_w * aspect

        fig, axes = plt.subplots(n_rows, n_cols,
                                 figsize=(total_width_inch + 0.8,
                                          panel_h * n_rows + 0.3 * n_rows))
        if n_rows == 1:
            axes = axes[np.newaxis, :]

        col_titles = [
            "(a) Input",
            r"(b) $\sigma_I$",
            r"(c) $\sigma_P$",
            r"(d) $M_I$",
            r"(e) $M_P$",
        ]

        for r, scene in enumerate(scene_list):
            rgb = scene["rgb"]
            # 第一列列标题只在第一行显示
            show_title = (r == 0)

            axes[r, 0].imshow(rgb)
            if show_title:
                axes[r, 0].set_title(col_titles[0], fontsize=9, pad=3)
            axes[r, 0].axis("off")

            # 行标签
            label = scene.get("label", "")
            if label:
                axes[r, 0].set_ylabel(label, fontsize=8, rotation=90,
                                       labelpad=10)

            show_cb = (r == n_rows - 1)  # 只在最后一行显示 colorbar

            _paper_overlay(axes[r, 1], rgb, scene["map_ui"], "inferno",
                           col_titles[1] if show_title else "",
                           fig, vmin=u_vmin, vmax=u_vmax, alpha=alpha,
                           show_colorbar=show_cb)
            _paper_overlay(axes[r, 2], rgb, scene["map_up"], "inferno",
                           col_titles[2] if show_title else "",
                           fig, vmin=u_vmin, vmax=u_vmax, alpha=alpha,
                           show_colorbar=show_cb)
            _paper_overlay(axes[r, 3], rgb, scene["map_mi"], "viridis",
                           col_titles[3] if show_title else "",
                           fig, vmin=0, vmax=1, alpha=alpha,
                           show_colorbar=show_cb)
            _paper_overlay(axes[r, 4], rgb, scene["map_mp"], "viridis",
                           col_titles[4] if show_title else "",
                           fig, vmin=0, vmax=1, alpha=alpha,
                           show_colorbar=show_cb)

        fig.tight_layout(pad=0.3, h_pad=0.5, w_pad=0.3)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        base, _ = os.path.splitext(out_path)
        fig.savefig(base + ".pdf", format="pdf")
        fig.savefig(base + ".png", format="png")
        plt.close(fig)


# =====================================================================
# 4. 主入口：在 validation_step 中调用
# =====================================================================

def maybe_visualize_puaf(model, data_dict, batch_idx, current_epoch, log_dir, args):
    """
    在 validation_step 中调用。根据 config 决定是否执行可视化。

    Args:
        model:          LightningModule (get_model 实例)
        data_dict:      forward 后的 data_dict（含 img, img_indices, batch_idx 等）
        batch_idx:      当前 val batch index
        current_epoch:  当前 epoch
        log_dir:        日志根目录
        args:           config dict（EasyDict / dict）
    """
    vis_cfg = args.get("train_params", {}).get("puaf_vis", None)
    if vis_cfg is None or not vis_cfg.get("enabled", False):
        if batch_idx == 0:
            print("[puaf_vis] SKIP: puaf_vis not enabled or missing in config")
        return
    if not HAS_MPL:
        if batch_idx == 0:
            print("[puaf_vis] SKIP: matplotlib not available")
        return

    interval = vis_cfg.get("vis_interval", 10)
    if current_epoch % interval != 0:
        if batch_idx == 0:
            print(f"[puaf_vis] SKIP: epoch {current_epoch} % interval {interval} != 0")
        return

    max_frames = vis_cfg.get("max_frames", 8)
    if batch_idx >= max_frames:
        return

    if batch_idx == 0:
        print(f"[puaf_vis] epoch={current_epoch}, log_dir={log_dir}, max_frames={max_frames}")

    # 检查 fusion modules 是否有 UGAF
    fusion = getattr(model, "fusion", None)
    if fusion is None:
        if batch_idx == 0:
            print("[puaf_vis] SKIP: model has no 'fusion' attribute")
        return
    fusion_modules = getattr(fusion, "fusion_modules", None)
    if fusion_modules is None:
        if batch_idx == 0:
            print("[puaf_vis] SKIP: fusion has no 'fusion_modules'")
        return

    # 确保已插桩
    instrumented = instrument_ugaf_modules(model)
    if len(instrumented) == 0:
        if batch_idx == 0:
            print("[puaf_vis] SKIP: no UGAF modules found to instrument")
        return

    scale_idx = vis_cfg.get("scale_idx", -1)
    n_scales = len(fusion_modules)
    if scale_idx < 0:
        scale_idx = n_scales + scale_idx
    if scale_idx < 0 or scale_idx >= n_scales:
        if batch_idx == 0:
            print(f"[puaf_vis] SKIP: scale_idx={scale_idx} out of range [0, {n_scales})")
        return

    ugaf = instrumented[min(scale_idx, len(instrumented) - 1)][1]
    unc = getattr(ugaf, "_last_uncertainty", None)
    if unc is None:
        if batch_idx == 0:
            print("[puaf_vis] SKIP: _last_uncertainty is None (forward did not run 2D+fusion path?)")
        return

    if batch_idx == 0:
        unc_len = unc["u_img"].shape[0]
        total_pts = sum(len(x) for x in data_dict["img_indices"])
        print(f"[puaf_vis] OK: unc_len={unc_len}, total_img_pts={total_pts}, "
              f"bsz={len(data_dict['img_indices'])}")

    # 提取数据
    top_pctl = vis_cfg.get("top_percentile", 95)
    out_subdir = vis_cfg.get("out_dir", "vis_puaf")
    out_root = os.path.join(log_dir, out_subdir, f"epoch_{current_epoch}")
    normalizer = args.get("dataset_params", {}).get("image_normalizer", None)

    bsz = len(data_dict["img_indices"])
    lengths = [len(x) for x in data_dict["img_indices"]]

    cursor = 0
    for i in range(bsz):
        n_i = lengths[i]
        sl = slice(cursor, cursor + n_i)
        cursor += n_i

        # 安全切片：uncertainty tensor 可能比 img_indices 短
        unc_len = unc["u_img"].shape[0]
        if sl.stop > unc_len:
            print(f"[puaf_vis] WARNING: unc length={unc_len} < slice {sl}, skip sample {i}")
            continue

        ui = unc["u_img"][sl].detach().cpu().numpy().reshape(-1)
        up = unc["u_pts"][sl].detach().cpu().numpy().reshape(-1)
        mi = unc["M_img"][sl].detach().cpu().numpy().reshape(-1)
        mp = unc["M_pts"][sl].detach().cpu().numpy().reshape(-1)

        if ui.size == 0 or up.size == 0:
            print(f"[puaf_vis] WARNING: empty uncertainty arrays for sample {i}, skip")
            continue

        img_idx = data_dict["img_indices"][i]
        if torch.is_tensor(img_idx):
            img_idx = img_idx.detach().cpu().numpy()

        img_shape = data_dict["img_shape"][i]
        h, w = int(img_shape[0]), int(img_shape[1])

        rgb = denorm_image(data_dict["img"][i], img_shape, normalizer)

        sigma = vis_cfg.get("gauss_sigma", 5.0)
        map_ui = rasterize_to_image(img_idx, ui, h, w, sigma=sigma)
        map_up = rasterize_to_image(img_idx, up, h, w, sigma=sigma)
        map_mi = rasterize_to_image(img_idx, mi, h, w, sigma=sigma)
        map_mp = rasterize_to_image(img_idx, mp, h, w, sigma=sigma)

        path_info = data_dict.get("path", [""])[i] if i < len(data_dict.get("path", [])) else ""
        frame_name = os.path.splitext(os.path.basename(str(path_info)))[0]
        out_png = os.path.join(out_root, f"batch{batch_idx}_sample{i}_{frame_name}.png")

        title = f"PUAF Uncertainty — epoch {current_epoch}"
        subtitle = f"path={path_info}  |  uI_mean={np.mean(ui):.4f}  uP_mean={np.mean(up):.4f}  MI_mean={np.mean(mi):.4f}  MP_mean={np.mean(mp):.4f}"

        draw_uncertainty_figure(
            rgb, map_ui, map_up, map_mi, map_mp,
            ui, up, mi, mp,
            title=title, subtitle=subtitle, out_path=out_png,
        )

        # ---------- 论文模式 ----------
        paper_mode = vis_cfg.get("paper_mode", False)
        if paper_mode:
            alpha_paper = vis_cfg.get("overlay_alpha", 0.6)

            # 1) 保存 .npz 原始数据（离线重新排版用）
            npz_path = os.path.join(out_root, f"batch{batch_idx}_sample{i}_{frame_name}.npz")
            np.savez_compressed(
                npz_path,
                rgb=rgb,                    # (H,W,3) float32
                map_ui=map_ui,              # (H,W) float32, NaN where no data
                map_up=map_up,
                map_mi=map_mi,
                map_mp=map_mp,
                ui_vals=ui,                 # (N,) raw per-point values
                up_vals=up,
                mi_vals=mi,
                mp_vals=mp,
                img_indices=img_idx,        # (N,2) for re-rasterization
                epoch=current_epoch,
                path=str(path_info),
                sigma=sigma,
            )

            # 2) 输出论文级单场景行条图 (PDF + PNG)
            paper_path = os.path.join(out_root, "paper",
                                      f"batch{batch_idx}_sample{i}_{frame_name}")
            draw_paper_figure(
                rgb, map_ui, map_up, map_mi, map_mp,
                ui, up,
                out_path=paper_path,
                alpha=alpha_paper,
                scene_label=frame_name,
            )

import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from wcs_unified.spvcnn_encoder import SPVCNNFeatureEncoder

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENSCENE_ROOT = REPO_ROOT / "openscene"
if str(OPENSCENE_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENSCENE_ROOT))


class SimpleTextTokenEncoder(nn.Module):
    def __init__(self, vocab_size: int = 8192, embed_dim: int = 256, out_dim: int = 128, max_tokens: int = 32):
        super().__init__()
        self.vocab_size = vocab_size
        self.max_tokens = max_tokens
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.proj = nn.Sequential(
            nn.LayerNorm(embed_dim),
            nn.Linear(embed_dim, out_dim),
            nn.ReLU(True),
            nn.Linear(out_dim, out_dim),
        )

    def _token_to_id(self, token: str) -> int:
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        return int(digest, 16) % self.vocab_size

    def _tokenize(self, text: str, device: torch.device) -> torch.Tensor:
        tokens = text.lower().strip().split()
        if not tokens:
            tokens = ["empty"]
        ids = [self._token_to_id(tok) for tok in tokens[: self.max_tokens]]
        return torch.tensor(ids, dtype=torch.long, device=device)

    def forward(self, texts: List[str], device: torch.device) -> torch.Tensor:
        token_lists = [self._tokenize(text, device) for text in texts]
        max_len = max(ids.shape[0] for ids in token_lists)
        padded = torch.zeros(len(token_lists), max_len, dtype=torch.long, device=device)
        for i, ids in enumerate(token_lists):
            padded[i, : ids.shape[0]] = ids
        emb = self.embedding(padded)
        return self.proj(emb)


class ClipTextTokenEncoder(nn.Module):
    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "openai",
        out_dim: int = 128,
        local_dir: Optional[str] = None,
        token_length: int = 4,
    ) -> None:
        super().__init__()
        self.token_length = token_length
        self.backend: Optional[str] = None
        self.tokenizer = None
        self.clip_model = None

        try:
            import open_clip  # type: ignore

            self.backend = "open_clip"
            self.tokenizer = open_clip.get_tokenizer(model_name)
            if local_dir:
                local_weight_path = None
                for candidate in ("open_clip_pytorch_model.bin", "pytorch_model.bin", "open_clip_model.safetensors"):
                    candidate_path = os.path.join(local_dir, candidate)
                    if os.path.exists(candidate_path):
                        local_weight_path = candidate_path
                        break
                if local_weight_path is None:
                    raise FileNotFoundError(f"No CLIP weight file found under local_dir={local_dir}")
                self.clip_model, _, _ = open_clip.create_model_and_transforms(
                    model_name=model_name,
                    pretrained=local_weight_path,
                )
            else:
                self.clip_model, _, _ = open_clip.create_model_and_transforms(
                    model_name=model_name,
                    pretrained=pretrained,
                )
            width = int(self.clip_model.text_projection.shape[1])
        except Exception as exc:
            raise ImportError("ClipTextTokenEncoder requires open_clip with available weights.") from exc

        for param in self.clip_model.parameters():
            param.requires_grad = False

        self.proj = nn.Sequential(
            nn.LayerNorm(width),
            nn.Linear(width, out_dim),
            nn.ReLU(True),
            nn.Linear(out_dim, out_dim),
        )
        self.pos_embed = nn.Parameter(torch.zeros(1, token_length, out_dim))

    def forward(self, texts: List[str], device: torch.device) -> torch.Tensor:
        self.clip_model = self.clip_model.to(device)
        tokens = self.tokenizer(texts).to(device)
        with torch.no_grad():
            global_feat = self.clip_model.encode_text(tokens).float()
        token = self.proj(global_feat).unsqueeze(1)
        token = token.expand(-1, self.token_length, -1)
        return token + self.pos_embed


class ImageTokenEncoder(nn.Module):
    def __init__(self, out_dim: int = 128, token_grid: int = 16) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(True),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(True),
            nn.Conv2d(64, out_dim, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(out_dim),
            nn.ReLU(True),
        )
        self.token_grid = token_grid

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        feat = self.stem(images)
        feat = F.adaptive_avg_pool2d(feat, output_size=(self.token_grid, self.token_grid))
        return feat.flatten(2).transpose(1, 2).contiguous()


class OrthoSpatialPriorEncoder(nn.Module):
    def __init__(self, out_dim: int = 128, token_grid: int = 16, y_flip: bool = True) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(True),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(True),
            nn.Conv2d(64, out_dim, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(out_dim),
            nn.ReLU(True),
        )
        self.token_grid = token_grid
        self.y_flip = bool(y_flip)

    def _build_sampling_grid(
        self, points_xyz: torch.Tensor, valid_point_mask: Optional[torch.Tensor]
    ) -> torch.Tensor:
        batch_size, num_points = points_xyz.shape[:2]
        grid = points_xyz.new_zeros((batch_size, num_points, 1, 2))
        xy = points_xyz[:, :, :2]

        for batch_idx in range(batch_size):
            if valid_point_mask is not None:
                point_mask = valid_point_mask[batch_idx]
            else:
                point_mask = torch.ones(num_points, dtype=torch.bool, device=points_xyz.device)
            if not point_mask.any():
                continue

            xy_i = xy[batch_idx][point_mask]
            xy_min = xy_i.min(dim=0).values
            xy_max = xy_i.max(dim=0).values
            xy_range = (xy_max - xy_min).clamp_min(1e-6)
            xy_norm = (xy_i - xy_min) / xy_range

            grid_x = xy_norm[:, 0] * 2.0 - 1.0
            if self.y_flip:
                grid_y = 1.0 - xy_norm[:, 1] * 2.0
            else:
                grid_y = xy_norm[:, 1] * 2.0 - 1.0

            grid_i = torch.stack([grid_x, grid_y], dim=-1)
            grid[batch_idx, point_mask, 0, :] = grid_i

        return grid

    def forward(
        self,
        images: torch.Tensor,
        points_xyz: torch.Tensor,
        valid_point_mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        feat_map = self.stem(images)
        tokens = F.adaptive_avg_pool2d(feat_map, output_size=(self.token_grid, self.token_grid))
        tokens = tokens.flatten(2).transpose(1, 2).contiguous()

        sample_grid = self._build_sampling_grid(points_xyz, valid_point_mask)
        point_feat = F.grid_sample(
            feat_map,
            sample_grid,
            mode="bilinear",
            padding_mode="border",
            align_corners=True,
        )
        point_feat = point_feat.squeeze(-1).transpose(1, 2).contiguous()
        if valid_point_mask is not None:
            point_feat = point_feat * valid_point_mask.unsqueeze(-1).float()
        return tokens, point_feat


class PointMLPEncoder(nn.Module):
    def __init__(self, in_dim: int = 6, hidden_dim: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.ReLU(True),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(True),
            nn.Linear(hidden_dim, hidden_dim),
        )

    def forward(self, points_xyz: torch.Tensor, points_rgb: torch.Tensor, valid_point_mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        return self.net(torch.cat([points_xyz, points_rgb], dim=-1))


class OpenSceneSparsePointEncoder(nn.Module):
    def __init__(self, hidden_dim: int = 128, arch_3d: str = "MinkUNet18A", voxel_size: float = 0.05) -> None:
        super().__init__()
        try:
            import MinkowskiEngine as ME  # type: ignore
            from models.mink_unet import mink_unet  # type: ignore
        except Exception as exc:
            raise ImportError("OpenSceneSparsePointEncoder requires MinkowskiEngine and OpenScene model imports.") from exc

        self.ME = ME
        self.voxel_size = voxel_size
        self.backbone = mink_unet(in_channels=3, out_channels=hidden_dim, D=3, arch=arch_3d)

    def _voxelize_one(
        self, xyz: torch.Tensor, rgb: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        xyz_shift = xyz - xyz.min(dim=0, keepdim=True).values
        coords_int = torch.floor(xyz_shift / self.voxel_size).int()
        unique_coords, inverse = torch.unique(coords_int, dim=0, return_inverse=True)
        voxel_count = unique_coords.shape[0]

        voxel_feats = torch.zeros(voxel_count, rgb.shape[1], dtype=rgb.dtype, device=rgb.device)
        counts = torch.zeros(voxel_count, 1, dtype=rgb.dtype, device=rgb.device)
        voxel_feats.index_add_(0, inverse, rgb * 2.0 - 1.0)
        counts.index_add_(0, inverse, torch.ones(rgb.shape[0], 1, dtype=rgb.dtype, device=rgb.device))
        voxel_feats = voxel_feats / counts.clamp_min(1.0)
        return unique_coords, voxel_feats, inverse

    def forward(
        self, points_xyz: torch.Tensor, points_rgb: torch.Tensor, valid_point_mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        coords_list = []
        feats_list = []
        inverse_list = []
        voxel_counts = []
        point_masks = []

        for batch_idx in range(points_xyz.shape[0]):
            if valid_point_mask is not None:
                point_mask = valid_point_mask[batch_idx]
                xyz_i = points_xyz[batch_idx][point_mask]
                rgb_i = points_rgb[batch_idx][point_mask]
            else:
                point_mask = None
                xyz_i = points_xyz[batch_idx]
                rgb_i = points_rgb[batch_idx]

            coords_i, feats_i, inverse_i = self._voxelize_one(xyz_i, rgb_i)
            # MinkowskiEngine 0.5.x internally floors coordinates inside
            # batched_coordinates; passing Int tensors on CUDA can trigger
            # "floor_cuda not implemented for 'Int'". Keep these as float.
            coords_list.append(coords_i.float())
            feats_list.append(feats_i)
            inverse_list.append(inverse_i)
            voxel_counts.append(coords_i.shape[0])
            point_masks.append(point_mask)

        coords = self.ME.utils.batched_coordinates(coords_list, device=points_xyz.device)
        feats = torch.cat(feats_list, dim=0).to(points_xyz.device)
        sparse = self.ME.SparseTensor(features=feats, coordinates=coords)
        out_sparse = self.backbone(sparse)
        if hasattr(out_sparse, "F"):
            out_feats = out_sparse.F
        else:
            out_feats = out_sparse

        outputs = []
        offset = 0
        for batch_idx, voxel_count in enumerate(voxel_counts):
            voxel_feat_i = out_feats[offset : offset + voxel_count]
            point_feat_i = voxel_feat_i[inverse_list[batch_idx]]
            if point_masks[batch_idx] is not None:
                padded_feat_i = torch.zeros(
                    points_xyz.shape[1], point_feat_i.shape[1], dtype=point_feat_i.dtype, device=point_feat_i.device
                )
                padded_feat_i[point_masks[batch_idx]] = point_feat_i
                outputs.append(padded_feat_i)
            else:
                outputs.append(point_feat_i)
            offset += voxel_count
        return torch.stack(outputs, dim=0)


class GUFNetSPVPointEncoder(nn.Module):
    def __init__(
        self,
        hidden_dim: int = 128,
        input_dims: int = 6,
        scale_list: Tuple[int, ...] = (2, 4, 8, 16),
        spatial_shape: Tuple[int, int, int] = (23088, 73472, 880),
        min_volume_space: Tuple[float, float, float] = (-4654.0, -5286.0, -88.0),
        max_volume_space: Tuple[float, float, float] = (1116.0, 13082.0, 129.0),
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.input_dims = input_dims
        try:
            self.encoder = SPVCNNFeatureEncoder(
                input_dims=self.input_dims,
                hidden_dim=self.hidden_dim,
                scale_list=tuple(scale_list),
                spatial_shape=tuple(spatial_shape),
                min_volume_space=tuple(min_volume_space),
                max_volume_space=tuple(max_volume_space),
            )
        except Exception as exc:
            raise ImportError(
                "GUFNetSPVPointEncoder requires spconv, torch_scatter, and local SPVCNN encoder dependencies."
            ) from exc

        self.out_proj = nn.Sequential(
            nn.LayerNorm(self.hidden_dim * len(scale_list)),
            nn.Linear(self.hidden_dim * len(scale_list), self.hidden_dim),
            nn.GELU(),
            nn.Linear(self.hidden_dim, self.hidden_dim),
        )

    def forward(
        self, points_xyz: torch.Tensor, points_rgb: torch.Tensor, valid_point_mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        device = points_xyz.device
        batch_size = points_xyz.shape[0]
        max_points = points_xyz.shape[1]

        points_list = []
        batch_indices = []
        point_masks = []
        for batch_idx in range(batch_size):
            if valid_point_mask is not None:
                point_mask = valid_point_mask[batch_idx]
            else:
                point_mask = torch.ones(max_points, dtype=torch.bool, device=device)

            xyz_i = points_xyz[batch_idx][point_mask]
            rgb_i = points_rgb[batch_idx][point_mask]
            pts_i = torch.cat([xyz_i, rgb_i], dim=1)

            points_list.append(pts_i)
            batch_indices.append(torch.full((pts_i.shape[0],), batch_idx, dtype=torch.long, device=device))
            point_masks.append(point_mask)

        flat_points = torch.cat(points_list, dim=0)
        flat_batch_idx = torch.cat(batch_indices, dim=0)
        data_dict = {
            "points": flat_points,
            "batch_idx": flat_batch_idx,
            "batch_size": batch_size,
        }
        point_feat = self.encoder(data_dict)
        point_feat = self.out_proj(point_feat)

        outputs = []
        cursor = 0
        for batch_idx in range(batch_size):
            count = points_list[batch_idx].shape[0]
            point_feat_i = point_feat[cursor : cursor + count]
            padded_feat_i = torch.zeros(max_points, point_feat_i.shape[1], dtype=point_feat_i.dtype, device=device)
            padded_feat_i[point_masks[batch_idx]] = point_feat_i
            outputs.append(padded_feat_i)
            cursor += count

        return torch.stack(outputs, dim=0)


class CrossAttentionBlock(nn.Module):
    def __init__(self, dim: int = 128, num_heads: int = 4, dropout: float = 0.0, query_chunk_size: int = 4096) -> None:
        super().__init__()
        self.norm_q = nn.LayerNorm(dim)
        self.norm_kv = nn.LayerNorm(dim)
        self.attn = nn.MultiheadAttention(dim, num_heads=num_heads, dropout=dropout)
        self.ffn = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Linear(dim, dim * 2),
            nn.GELU(),
            nn.Linear(dim * 2, dim),
        )
        self.query_chunk_size = int(query_chunk_size)

    def forward(self, query: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        context_t = self.norm_kv(context).transpose(0, 1)
        outputs = []
        chunk_size = max(self.query_chunk_size, 1)
        for start in range(0, query.shape[1], chunk_size):
            query_chunk = query[:, start : start + chunk_size, :]
            query_t = self.norm_q(query_chunk).transpose(0, 1)
            attended, _ = self.attn(query_t, context_t, context_t, need_weights=False)
            attended = attended.transpose(0, 1)
            query_chunk = query_chunk + attended
            query_chunk = query_chunk + self.ffn(query_chunk)
            outputs.append(query_chunk)
        return torch.cat(outputs, dim=1)


class PointRefineBlock(nn.Module):
    def __init__(self, dim: int = 128, chunk_size: int = 4096) -> None:
        super().__init__()
        self.ffn = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Linear(dim, dim * 2),
            nn.GELU(),
            nn.Linear(dim * 2, dim),
        )
        self.chunk_size = int(chunk_size)

    def forward(self, point_tokens: torch.Tensor) -> torch.Tensor:
        outputs = []
        chunk_size = max(self.chunk_size, 1)
        for start in range(0, point_tokens.shape[1], chunk_size):
            chunk = point_tokens[:, start : start + chunk_size, :]
            outputs.append(chunk + self.ffn(chunk))
        return torch.cat(outputs, dim=1)


class QueryMaskHead(nn.Module):
    def __init__(self, hidden_dim: int = 128, chunk_size: int = 4096) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.LayerNorm(hidden_dim * 3),
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, 1),
        )
        self.chunk_size = int(chunk_size)

    def forward(self, point_tokens: torch.Tensor, query_tokens: torch.Tensor) -> torch.Tensor:
        outputs = []
        chunk_size = max(self.chunk_size, 1)
        for start in range(0, point_tokens.shape[1], chunk_size):
            point_chunk = point_tokens[:, start : start + chunk_size, :]
            query_expand = query_tokens.unsqueeze(1).expand(-1, point_chunk.shape[1], -1)
            fused = torch.cat([point_chunk, query_expand, point_chunk * query_expand], dim=-1)
            outputs.append(self.net(fused).squeeze(-1))
        return torch.cat(outputs, dim=1)


class AreaInvariantBottleneck(nn.Module):
    def __init__(self, hidden_dim: int = 128, bottleneck_ratio: float = 1.0, num_areas: int = 3) -> None:
        super().__init__()
        bottleneck_dim = max(int(hidden_dim * bottleneck_ratio), hidden_dim)
        self.inv_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, bottleneck_dim),
            nn.GELU(),
            nn.Linear(bottleneck_dim, hidden_dim),
        )
        self.style_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, bottleneck_dim),
            nn.GELU(),
            nn.Linear(bottleneck_dim, hidden_dim),
        )
        self.reconstruct = nn.Sequential(
            nn.LayerNorm(hidden_dim * 2),
            nn.Linear(hidden_dim * 2, bottleneck_dim),
            nn.GELU(),
            nn.Linear(bottleneck_dim, hidden_dim),
        )
        self.style_area_head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, num_areas),
        )
        self.inv_area_head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, num_areas),
        )

    @staticmethod
    def masked_mean(tokens: torch.Tensor, valid_point_mask: Optional[torch.Tensor]) -> torch.Tensor:
        if valid_point_mask is None:
            return tokens.mean(dim=1)
        weights = valid_point_mask.unsqueeze(-1).float()
        return (tokens * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1.0)

    def forward(self, fused_tokens: torch.Tensor, valid_point_mask: Optional[torch.Tensor] = None) -> Dict[str, torch.Tensor]:
        inv_tokens = self.inv_proj(fused_tokens)
        style_tokens = self.style_proj(fused_tokens)
        recon_tokens = self.reconstruct(torch.cat([inv_tokens, style_tokens], dim=-1))

        inv_pooled = self.masked_mean(inv_tokens, valid_point_mask)
        style_pooled = self.masked_mean(style_tokens, valid_point_mask)

        return {
            "inv_tokens": inv_tokens,
            "style_tokens": style_tokens,
            "recon_tokens": recon_tokens,
            "inv_pooled": inv_pooled,
            "style_pooled": style_pooled,
            "style_area_logits": self.style_area_head(style_pooled),
            "inv_area_logits": self.inv_area_head(inv_pooled),
        }


class CrossAreaPrototypeAlignmentHead(nn.Module):
    def __init__(self, hidden_dim: int = 128, prototype_dim: int = 128) -> None:
        super().__init__()
        self.prototype_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, prototype_dim),
            nn.GELU(),
            nn.Linear(prototype_dim, prototype_dim),
        )

    def project(self, inv_tokens: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.prototype_proj(inv_tokens), dim=-1)


class UnifiedSegPointStageA(nn.Module):
    def __init__(
        self,
        hidden_dim: int = 128,
        num_classes: int = 15,
        teacher_feature_dim: int = 768,
        geometry_feature_dim: int = 4,
        point_encoder_type: str = "mlp",
        text_encoder_type: str = "simple",
        clip_model_name: str = "ViT-B-32",
        clip_pretrained: str = "openai",
        clip_local_dir: Optional[str] = None,
        use_ortho_prior: bool = False,
        ortho_token_grid: int = 16,
        ortho_y_flip: bool = True,
        use_area_invariant_bottleneck: bool = False,
        area_bottleneck_ratio: float = 1.0,
        num_areas: int = 3,
        use_prototype_alignment: bool = False,
        prototype_dim: int = 128,
        voxel_size: float = 0.05,
        spv_scale_list: Tuple[int, ...] = (2, 4, 8, 16),
        spv_spatial_shape: Tuple[int, int, int] = (23088, 73472, 880),
        spv_min_volume_space: Tuple[float, float, float] = (-4654.0, -5286.0, -88.0),
        spv_max_volume_space: Tuple[float, float, float] = (1116.0, 13082.0, 129.0),
        point_chunk_size: int = 4096,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_classes = num_classes
        self.teacher_feature_dim = teacher_feature_dim
        self.geometry_feature_dim = geometry_feature_dim
        self.use_ortho_prior = bool(use_ortho_prior)
        self.use_area_invariant_bottleneck = bool(use_area_invariant_bottleneck)
        self.use_prototype_alignment = bool(use_prototype_alignment)
        self.num_areas = int(num_areas)

        if point_encoder_type == "openscene":
            try:
                self.point_encoder = OpenSceneSparsePointEncoder(
                    hidden_dim=hidden_dim,
                    arch_3d="MinkUNet18A",
                    voxel_size=voxel_size,
                )
                self.point_encoder_type = "openscene"
            except Exception as exc:
                raise RuntimeError(
                    "Failed to initialize point_encoder='openscene'. "
                    "Check MinkowskiEngine/OpenScene model imports and CUDA compatibility."
                ) from exc
        elif point_encoder_type == "spvcnn":
            try:
                self.point_encoder = GUFNetSPVPointEncoder(
                    hidden_dim=hidden_dim,
                    input_dims=6,
                    scale_list=tuple(spv_scale_list),
                    spatial_shape=tuple(spv_spatial_shape),
                    min_volume_space=tuple(spv_min_volume_space),
                    max_volume_space=tuple(spv_max_volume_space),
                )
                self.point_encoder_type = "spvcnn"
            except Exception as exc:
                raise RuntimeError(
                    "Failed to initialize point_encoder='spvcnn'. "
                    "Check spconv/torch_scatter installation and GUFNet dependencies."
                ) from exc
        else:
            self.point_encoder = PointMLPEncoder(in_dim=6, hidden_dim=hidden_dim)
            self.point_encoder_type = "mlp"

        if self.use_ortho_prior:
            self.image_encoder = OrthoSpatialPriorEncoder(
                out_dim=hidden_dim,
                token_grid=ortho_token_grid,
                y_flip=ortho_y_flip,
            )
            self.ortho_point_proj = nn.Sequential(
                nn.LayerNorm(hidden_dim),
                nn.Linear(hidden_dim, hidden_dim),
                nn.GELU(),
                nn.Linear(hidden_dim, hidden_dim),
            )
            self.ortho_point_gate = nn.Sequential(
                nn.LayerNorm(hidden_dim * 2),
                nn.Linear(hidden_dim * 2, hidden_dim),
                nn.GELU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.Sigmoid(),
            )
        else:
            self.image_encoder = ImageTokenEncoder(out_dim=hidden_dim, token_grid=16)
            self.ortho_point_proj = None
            self.ortho_point_gate = None
        self.geometry_proj = nn.Sequential(
            nn.LayerNorm(geometry_feature_dim),
            nn.Linear(geometry_feature_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.geometry_gate = nn.Sequential(
            nn.LayerNorm(hidden_dim * 2),
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Sigmoid(),
        )

        if text_encoder_type == "clip":
            try:
                self.text_encoder = ClipTextTokenEncoder(
                    model_name=clip_model_name,
                    pretrained=clip_pretrained,
                    out_dim=hidden_dim,
                    local_dir=clip_local_dir,
                )
                self.text_encoder_type = "clip"
            except Exception as exc:
                raise RuntimeError(
                    "Failed to initialize text_encoder='clip'. "
                    "Check open_clip installation, network access, and clip-local-dir contents."
                ) from exc
        else:
            self.text_encoder = SimpleTextTokenEncoder(out_dim=hidden_dim)
            self.text_encoder_type = "simple"

        self.text_to_point = CrossAttentionBlock(dim=hidden_dim, num_heads=4, query_chunk_size=point_chunk_size)
        self.image_to_point = CrossAttentionBlock(dim=hidden_dim, num_heads=4, query_chunk_size=point_chunk_size)
        self.point_refine = PointRefineBlock(dim=hidden_dim, chunk_size=point_chunk_size)
        if self.use_area_invariant_bottleneck:
            self.area_bottleneck = AreaInvariantBottleneck(
                hidden_dim=hidden_dim,
                bottleneck_ratio=area_bottleneck_ratio,
                num_areas=self.num_areas,
            )
        else:
            self.area_bottleneck = None
        if self.use_prototype_alignment:
            self.prototype_head = CrossAreaPrototypeAlignmentHead(hidden_dim=hidden_dim, prototype_dim=prototype_dim)
        else:
            self.prototype_head = None

        self.query_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
        )
        self.mask_head = QueryMaskHead(hidden_dim=hidden_dim, chunk_size=point_chunk_size)
        self.class_head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, num_classes),
        )
        self.open_vocab_head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, teacher_feature_dim),
        )
        self.query_open_vocab_head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, teacher_feature_dim),
        )
        self.open_vocab_chunk_size = 65536
        self.point_chunk_size = int(point_chunk_size)

    def project_open_vocab_points(self, point_tokens: torch.Tensor) -> torch.Tensor:
        if point_tokens.numel() == 0:
            return point_tokens.new_zeros((0, self.teacher_feature_dim))
        outputs = []
        for start in range(0, point_tokens.shape[0], self.open_vocab_chunk_size):
            chunk = point_tokens[start : start + self.open_vocab_chunk_size]
            chunk = F.normalize(self.open_vocab_head(chunk), dim=-1)
            outputs.append(chunk)
        return torch.cat(outputs, dim=0)

    def project_open_vocab_query(self, query_hidden: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.query_open_vocab_head(query_hidden), dim=-1)

    def forward(
        self,
        images: torch.Tensor,
        points_xyz: torch.Tensor,
        points_rgb: torch.Tensor,
        point_geometry_features: Optional[torch.Tensor],
        texts: List[str],
        valid_point_mask: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        device = points_xyz.device
        valid_mask_float = None
        if valid_point_mask is not None:
            valid_mask_float = valid_point_mask.unsqueeze(-1).float()

        if self.point_encoder_type in {"openscene", "spvcnn"}:
            point_tokens = self.point_encoder(points_xyz, points_rgb, valid_point_mask=valid_point_mask)
        else:
            point_tokens = self.point_encoder(points_xyz, points_rgb)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float
        if point_geometry_features is not None:
            geometry_tokens = self.geometry_proj(point_geometry_features.to(device))
            if valid_mask_float is not None:
                geometry_tokens = geometry_tokens * valid_mask_float
            geometry_gate = self.geometry_gate(torch.cat([point_tokens, geometry_tokens], dim=-1))
            point_tokens = point_tokens + geometry_gate * geometry_tokens
            if valid_mask_float is not None:
                point_tokens = point_tokens * valid_mask_float
        if self.use_ortho_prior:
            image_tokens, ortho_point_tokens = self.image_encoder(images, points_xyz, valid_point_mask=valid_point_mask)
            ortho_point_tokens = self.ortho_point_proj(ortho_point_tokens)
            if valid_mask_float is not None:
                ortho_point_tokens = ortho_point_tokens * valid_mask_float
            ortho_gate = self.ortho_point_gate(torch.cat([point_tokens, ortho_point_tokens], dim=-1))
            point_tokens = point_tokens + ortho_gate * ortho_point_tokens
            if valid_mask_float is not None:
                point_tokens = point_tokens * valid_mask_float
        else:
            image_tokens = self.image_encoder(images)
        text_tokens = self.text_encoder(texts, device=device)

        point_tokens = self.text_to_point(point_tokens, text_tokens)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float
        point_tokens = self.image_to_point(point_tokens, image_tokens)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float
        point_tokens = self.point_refine(point_tokens)
        if valid_mask_float is not None:
            point_tokens = point_tokens * valid_mask_float

        bottleneck_outputs = None
        if self.area_bottleneck is not None:
            bottleneck_input_tokens = point_tokens
            bottleneck_outputs = self.area_bottleneck(bottleneck_input_tokens, valid_point_mask=valid_point_mask)
            bottleneck_outputs["bottleneck_input_tokens"] = bottleneck_input_tokens
            point_tokens = bottleneck_outputs["inv_tokens"]
            if valid_mask_float is not None:
                point_tokens = point_tokens * valid_mask_float

        query_hidden = self.query_proj(text_tokens.mean(dim=1))
        class_logits_chunks = []
        for start in range(0, point_tokens.shape[1], max(self.point_chunk_size, 1)):
            class_logits_chunks.append(self.class_head(point_tokens[:, start : start + self.point_chunk_size, :]))
        class_logits = torch.cat(class_logits_chunks, dim=1)
        mask_logits = self.mask_head(point_tokens, query_hidden)

        outputs = {
            "point_tokens": point_tokens,
            "query_hidden": query_hidden,
            "class_logits": class_logits,
            "mask_logits": mask_logits,
        }
        if bottleneck_outputs is not None:
            outputs.update(bottleneck_outputs)
        if self.prototype_head is not None:
            outputs["prototype_tokens"] = self.prototype_head.project(point_tokens)
        return outputs

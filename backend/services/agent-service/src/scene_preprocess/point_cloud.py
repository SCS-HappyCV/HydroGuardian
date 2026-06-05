# 点云预处理工具。
# 第一版支持 ASCII PLY、XYZ、CSV、TXT 等文本点云，并参考 wcs_unified 的网格地形特征生成逻辑。

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable

from config import SCENE_PREPROCESS_GEOMETRY_CELL_SIZE

from .contract import ScenePreprocessError


FEATURE_NAMES = ("z_norm", "grid_slope", "grid_roughness", "grid_density")


# 读取点云字节并转换成 SceneTensorSample 需要的点级字段。
def preprocess_point_cloud_bytes(content: bytes, max_points: int) -> Dict[str, Any]:
    raw_points = _parse_point_cloud(content)
    if not raw_points:
        raise ScenePreprocessError("point cloud has no valid points")

    sampled_points = _sample_evenly(raw_points, max_points)
    sampled_xyz = [point[:3] for point in sampled_points]
    geometry_features = _compute_grid_geometry_features(
        sampled_xyz,
        cell_size=SCENE_PREPROCESS_GEOMETRY_CELL_SIZE,
    )
    normalized_xyz, normalization = _normalize_xyz(sampled_xyz)
    points_rgb = [_normalize_rgb(point[3:6]) for point in sampled_points]

    return {
        "points_xyz": normalized_xyz,
        "points_rgb": points_rgb,
        "point_geometry_features": geometry_features,
        "valid_point_mask": [True for _ in normalized_xyz],
        "metadata": {
            "point_count_original": len(raw_points),
            "point_count_sampled": len(sampled_points),
            "max_points": max_points,
            "normalization": normalization,
            "has_rgb": _has_non_default_rgb(raw_points),
            "geometry_feature_names": list(FEATURE_NAMES),
            "geometry_cell_size": SCENE_PREPROCESS_GEOMETRY_CELL_SIZE,
            "supported_formats": ["ascii_ply", "xyz", "csv", "txt"],
        },
    }


# 根据文件头自动选择 PLY 或普通文本解析。
def _parse_point_cloud(content: bytes) -> list[tuple[float, float, float, float, float, float]]:
    text = _decode_text(content)
    stripped = text.lstrip()
    if stripped.lower().startswith("ply"):
        return _parse_ascii_ply(stripped)
    return _parse_xyz_text(stripped.splitlines())


# 将点云字节按 UTF-8/GBK 尝试解码；MVP 暂不支持二进制 PLY/LAS。
def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ScenePreprocessError("point cloud must be a text format in MVP")


# 解析 ASCII PLY，按 header 中的 property 顺序取 x/y/z/r/g/b。
def _parse_ascii_ply(text: str) -> list[tuple[float, float, float, float, float, float]]:
    lines = text.splitlines()
    properties: list[str] = []
    vertex_count = 0
    data_start = -1
    in_vertex_element = False

    for index, line in enumerate(lines):
        normalized = line.strip().lower()
        if normalized.startswith("format") and "ascii" not in normalized:
            raise ScenePreprocessError("binary PLY is not supported in MVP")
        if normalized.startswith("element vertex"):
            parts = normalized.split()
            vertex_count = int(parts[-1]) if parts[-1].isdigit() else 0
            in_vertex_element = True
            continue
        if normalized.startswith("element ") and not normalized.startswith("element vertex"):
            in_vertex_element = False
        if in_vertex_element and normalized.startswith("property"):
            properties.append(normalized.split()[-1])
        if normalized == "end_header":
            data_start = index + 1
            break

    if data_start < 0:
        raise ScenePreprocessError("invalid PLY header")
    if not {"x", "y", "z"}.issubset(set(properties)):
        raise ScenePreprocessError("PLY must contain x/y/z properties")

    name_to_index = {name: idx for idx, name in enumerate(properties)}
    rows = lines[data_start:data_start + vertex_count] if vertex_count > 0 else lines[data_start:]
    return _rows_to_points(rows, name_to_index)


# 解析普通文本点云，默认前三列是 xyz，后面可选 rgb。
def _parse_xyz_text(lines: Iterable[str]) -> list[tuple[float, float, float, float, float, float]]:
    rows = [line for line in lines if line.strip() and not line.strip().startswith("#")]
    name_to_index = {"x": 0, "y": 1, "z": 2, "red": 3, "green": 4, "blue": 5}
    return _rows_to_points(rows, name_to_index)


# 将文本行转换为统一的 x/y/z/r/g/b 元组。
def _rows_to_points(
    rows: Iterable[str],
    name_to_index: Dict[str, int],
) -> list[tuple[float, float, float, float, float, float]]:
    points: list[tuple[float, float, float, float, float, float]] = []
    x_idx = name_to_index.get("x", 0)
    y_idx = name_to_index.get("y", 1)
    z_idx = name_to_index.get("z", 2)
    red_idx = _first_existing_index(name_to_index, "red", "r", "diffuse_red")
    green_idx = _first_existing_index(name_to_index, "green", "g", "diffuse_green")
    blue_idx = _first_existing_index(name_to_index, "blue", "b", "diffuse_blue")

    for row in rows:
        values = _numeric_values(row)
        if len(values) <= max(x_idx, y_idx, z_idx):
            continue
        red = values[red_idx] if red_idx is not None and len(values) > red_idx else 128.0
        green = values[green_idx] if green_idx is not None and len(values) > green_idx else 128.0
        blue = values[blue_idx] if blue_idx is not None and len(values) > blue_idx else 128.0
        points.append((values[x_idx], values[y_idx], values[z_idx], red, green, blue))
    return points


# 查找多个候选颜色字段中第一个存在的列下标。
def _first_existing_index(name_to_index: Dict[str, int], *names: str) -> int | None:
    for name in names:
        if name in name_to_index:
            return name_to_index[name]
    return None


# 从一行文本中提取数字，兼容空格、逗号和分号分隔。
def _numeric_values(row: str) -> list[float]:
    tokens = [token for token in re.split(r"[\s,;]+", row.strip()) if token]
    values: list[float] = []
    for token in tokens:
        try:
            values.append(float(token))
        except ValueError:
            return []
    return values


# 均匀采样点云，避免 JSON 样本过大，同时保留整体空间分布。
def _sample_evenly(
    points: list[tuple[float, float, float, float, float, float]],
    max_points: int,
) -> list[tuple[float, float, float, float, float, float]]:
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / max(max_points - 1, 1)
    return [points[round(index * step)] for index in range(max_points)]


# 将 xyz 平移到中心并按最大尺度归一化，减少不同场景尺度差异。
def _normalize_xyz(points_xyz: list[tuple[float, float, float]]) -> tuple[list[list[float]], Dict[str, Any]]:
    xs = [point[0] for point in points_xyz]
    ys = [point[1] for point in points_xyz]
    zs = [point[2] for point in points_xyz]
    center = [(min(values) + max(values)) / 2.0 for values in (xs, ys, zs)]
    spans = [max(values) - min(values) for values in (xs, ys, zs)]
    scale = max(max(spans), 1e-6)

    normalized = [
        [
            round((x - center[0]) / scale, 6),
            round((y - center[1]) / scale, 6),
            round((z - center[2]) / scale, 6),
        ]
        for x, y, z in points_xyz
    ]
    metadata = {
        "center": [round(value, 6) for value in center],
        "scale": round(scale, 6),
        "spans": [round(value, 6) for value in spans],
    }
    return normalized, metadata


# 将 RGB 统一归一化到 0-1。
def _normalize_rgb(values: tuple[float, float, float]) -> list[float]:
    if max(values) > 1.0:
        return [round(max(0.0, min(value, 255.0)) / 255.0, 6) for value in values]
    return [round(max(0.0, min(value, 1.0)), 6) for value in values]


# 粗略判断输入点云是否携带了真实 RGB，而不是使用默认灰色兜底。
def _has_non_default_rgb(points: list[tuple[float, float, float, float, float, float]]) -> bool:
    return any(point[3:6] != (128.0, 128.0, 128.0) for point in points)


# 参考 wcs_unified.geometry_features.compute_grid_geometry_features 生成网格几何特征。
def _compute_grid_geometry_features(
    points_xyz: list[tuple[float, float, float]],
    *,
    cell_size: float,
) -> list[list[float]]:
    if not points_xyz:
        return []

    z_values = [point[2] for point in points_xyz]
    z_mean = sum(z_values) / len(z_values)
    z_std = math.sqrt(sum((z - z_mean) ** 2 for z in z_values) / len(z_values))
    z_std = max(z_std, 1e-6)
    z_norm = [(z - z_mean) / z_std for z in z_values]

    safe_cell_size = max(float(cell_size), 1e-6)
    min_x = min(point[0] for point in points_xyz)
    min_y = min(point[1] for point in points_xyz)
    point_cells = [
        (
            math.floor((point[0] - min_x) / safe_cell_size),
            math.floor((point[1] - min_y) / safe_cell_size),
        )
        for point in points_xyz
    ]
    cell_stats = _build_cell_stats(point_cells, z_values, safe_cell_size)
    slope_by_cell = _build_slope_by_cell(cell_stats, safe_cell_size)

    # 每个点继承所在网格的 slope / roughness / density，和参考 PyTorch 实现保持一致。
    return [
        [
            round(z_norm[index], 6),
            round(slope_by_cell.get(cell, 0.0), 6),
            round(cell_stats[cell]["roughness"], 6),
            round(cell_stats[cell]["density"], 6),
        ]
        for index, cell in enumerate(point_cells)
    ]


# 汇总每个 XY 网格内的点数、平均高程、粗糙度和密度。
def _build_cell_stats(
    point_cells: list[tuple[int, int]],
    z_values: list[float],
    cell_size: float,
) -> Dict[tuple[int, int], Dict[str, float]]:
    stats: Dict[tuple[int, int], Dict[str, float]] = {}
    for cell, z in zip(point_cells, z_values):
        item = stats.setdefault(cell, {"count": 0.0, "z_sum": 0.0, "z2_sum": 0.0})
        item["count"] += 1.0
        item["z_sum"] += z
        item["z2_sum"] += z * z

    for item in stats.values():
        count = max(item["count"], 1.0)
        mean_z = item["z_sum"] / count
        variance = max(item["z2_sum"] / count - mean_z * mean_z, 0.0)
        item["mean_z"] = mean_z
        item["roughness"] = math.sqrt(variance)
        item["density"] = count / (cell_size * cell_size)
    return stats


# 根据相邻网格平均高程差估计坡度。
def _build_slope_by_cell(
    cell_stats: Dict[tuple[int, int], Dict[str, float]],
    cell_size: float,
) -> Dict[tuple[int, int], float]:
    slope_by_cell: Dict[tuple[int, int], float] = {}
    for gx, gy in cell_stats:
        current = cell_stats[(gx, gy)]
        left = cell_stats.get((gx - 1, gy))
        right = cell_stats.get((gx + 1, gy))
        down = cell_stats.get((gx, gy - 1))
        up = cell_stats.get((gx, gy + 1))

        dzdx = _neighbor_gradient(current, left, right, cell_size)
        dzdy = _neighbor_gradient(current, down, up, cell_size)
        slope_by_cell[(gx, gy)] = math.sqrt(dzdx * dzdx + dzdy * dzdy)
    return slope_by_cell


# 计算一维相邻网格上的高程梯度，兼容只有单侧邻居的边界网格。
def _neighbor_gradient(
    current: Dict[str, float],
    previous_cell: Dict[str, float] | None,
    next_cell: Dict[str, float] | None,
    cell_size: float,
) -> float:
    if previous_cell is not None and next_cell is not None:
        return (next_cell["mean_z"] - previous_cell["mean_z"]) / (2.0 * cell_size)
    if previous_cell is not None:
        return (current["mean_z"] - previous_cell["mean_z"]) / cell_size
    if next_cell is not None:
        return (next_cell["mean_z"] - current["mean_z"]) / cell_size
    return 0.0

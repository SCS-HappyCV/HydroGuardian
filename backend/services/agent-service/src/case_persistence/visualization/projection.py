# 二维风险投影工具。
# 本模块把 EvidencePack 的 3D 候选区域轻量投影到主图像显示坐标，供正射图风险框使用。
from __future__ import annotations

from typing import Any, Dict


# 根据候选区域 3D bbox 生成图像像素 bbox 和四角 polygon。
def project_region_to_image(region: Dict[str, Any], display_width: int, display_height: int) -> Dict[str, Any]:
    bbox_min = _float_list(region.get("bbox_min"), 3)
    bbox_max = _float_list(region.get("bbox_max"), 3)
    if not bbox_min or not bbox_max or display_width <= 0 or display_height <= 0:
        return {}

    x_min = min(bbox_min[0], bbox_max[0])
    x_max = max(bbox_min[0], bbox_max[0])
    y_min = min(bbox_min[1], bbox_max[1])
    y_max = max(bbox_min[1], bbox_max[1])

    # 预处理坐标是以点云中心为原点的归一化坐标；这里先按 [-0.5, 0.5] 映射到图像。
    left = _normalized_x_to_pixel(x_min, display_width)
    right = _normalized_x_to_pixel(x_max, display_width)
    top = _normalized_y_to_pixel(y_max, display_height)
    bottom = _normalized_y_to_pixel(y_min, display_height)

    left, right = min(left, right), max(left, right)
    top, bottom = min(top, bottom), max(top, bottom)
    width = max(1.0, right - left)
    height = max(1.0, bottom - top)

    return {
        "bbox_pixel": {
            "x": round(left, 2),
            "y": round(top, 2),
            "width": round(width, 2),
            "height": round(height, 2),
        },
        "polygon_pixel": [
            {"x": round(left, 2), "y": round(top, 2)},
            {"x": round(right, 2), "y": round(top, 2)},
            {"x": round(right, 2), "y": round(bottom, 2)},
            {"x": round(left, 2), "y": round(bottom, 2)},
        ],
        "projection_mode": "normalized_xy_to_resized_pixel",
        "projection_confidence": "inferred",
    }


# 将候选区域 bbox 转成统一 3D bbox 字段。
def build_region_bbox_3d(region: Dict[str, Any]) -> Dict[str, Any]:
    bbox_min = _float_list(region.get("bbox_min"), 3)
    bbox_max = _float_list(region.get("bbox_max"), 3)
    if not bbox_min or not bbox_max:
        return {}
    return {
        "min": bbox_min,
        "max": bbox_max,
    }


# 将归一化 x 坐标映射到图像横向像素。
def _normalized_x_to_pixel(value: float, width: int) -> float:
    return _clamp((value + 0.5) * float(width), 0.0, float(width))


# 将归一化 y 坐标映射到图像纵向像素；图像坐标 y 轴向下，所以这里需要反转。
def _normalized_y_to_pixel(value: float, height: int) -> float:
    return _clamp((0.5 - value) * float(height), 0.0, float(height))


# 把输入转成指定长度的 float 列表，缺失或异常时返回空列表。
def _float_list(value: Any, min_length: int) -> list[float]:
    if not isinstance(value, list) or len(value) < min_length:
        return []
    try:
        return [round(float(item), 6) for item in value[:min_length]]
    except (TypeError, ValueError):
        return []


# 限制数值范围，避免异常区域把前端框画出容器。
def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))

# 图像预处理工具。
# 第一版把上传图像转换为 RGB、固定尺寸和 [3,H,W] 的 0-1 浮点数组。

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict

from PIL import Image, UnidentifiedImageError

from .contract import ScenePreprocessError


# 读取图像字节并转换成 SceneTensorSample 需要的通道优先数组。
def preprocess_image_bytes(content: bytes, image_size: int) -> tuple[list[list[list[float]]], Dict[str, Any]]:
    if not content:
        raise ScenePreprocessError("image content is empty")
    try:
        with Image.open(BytesIO(content)) as image:
            original_width, original_height = image.size
            rgb_image = image.convert("RGB")
            resized = rgb_image.resize((image_size, image_size), Image.Resampling.BILINEAR)
            tensor = _image_to_chw_tensor(resized)
    except UnidentifiedImageError as exc:
        raise ScenePreprocessError("image file is not a supported image format") from exc
    except Exception as exc:
        raise ScenePreprocessError(f"failed to preprocess image: {exc}") from exc

    metadata = {
        "original_width": original_width,
        "original_height": original_height,
        "image_size": image_size,
        "channels": 3,
        "normalization": "rgb_0_1",
    }
    return tensor, metadata


# 将 PIL 图像转成 [3,H,W]，避免后续模型输入通道顺序含混。
def _image_to_chw_tensor(image: Image.Image) -> list[list[list[float]]]:
    width, height = image.size
    channels = [
        [[0.0 for _ in range(width)] for _ in range(height)]
        for _ in range(3)
    ]
    pixels = image.load()

    # 这里按行列展开，保持 JSON 结构稳定；MVP 默认 64x64，不会形成过大的内存压力。
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            channels[0][y][x] = round(red / 255.0, 6)
            channels[1][y][x] = round(green / 255.0, 6)
            channels[2][y][x] = round(blue / 255.0, 6)
    return channels

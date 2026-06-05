# 真实场景预处理包。
# 对外只暴露请求/响应结构和总编排函数，具体图像、点云和 manifest 注册逻辑放在子模块中。

from .contract import (
    ScenePreprocessError,
    ScenePreprocessRequest,
    ScenePreprocessResult,
    ScenePreprocessValidationError,
)
from .service import preprocess_scene

__all__ = [
    "ScenePreprocessError",
    "ScenePreprocessRequest",
    "ScenePreprocessResult",
    "ScenePreprocessValidationError",
    "preprocess_scene",
]

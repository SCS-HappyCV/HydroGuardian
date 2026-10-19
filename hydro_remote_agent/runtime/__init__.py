"""Expert runtime contracts with lazy imports for model-heavy adapters."""

from importlib import import_module

from .adapter import ExpertAdapter
from .contracts import (
    ExpertConfigurationError,
    ExpertError,
    ExpertHealth,
    ExpertNotReadyError,
    ExpertResult,
    ExpertRuntimeError,
)
from .expert_runtime import (
    ExpertRuntime,
    build_mock_runtime,
    build_remote_runtime,
    load_expert_runtime,
    overlay_remote_tools,
)
from .remote_adapter import RemoteExpertAdapter, RemoteExpertError


_LAZY_EXPORTS = {
    "ChangeDetectionAdapter": (".change_detection_adapter", "ChangeDetectionAdapter"),
    "ChangeDetectionInferenceEngine": (".change_detection_engine", "ChangeDetectionInferenceEngine"),
    "GeometryRelationAdapter": (".geometry_adapter", "GeometryRelationAdapter"),
    "GufnetInferenceEngine": (".gufnet_engine", "GufnetInferenceEngine"),
    "HydroProgram3DAdapter": (".hydro_program3d_adapter", "HydroProgram3DAdapter"),
    "HydroProgram3DInferenceEngine": (".hydro_program3d_engine", "HydroProgram3DInferenceEngine"),
    "MultimodalGufnetAdapter": (".gufnet_adapter", "MultimodalGufnetAdapter"),
    "PointGufnetAdapter": (".gufnet_adapter", "PointGufnetAdapter"),
    "PointceptPtv3Adapter": (".pointcept_adapter", "PointceptPtv3Adapter"),
    "PointceptPtv3InferenceEngine": (".pointcept_engine", "PointceptPtv3InferenceEngine"),
    "MockExpertAdapter": (".mock_adapter", "MockExpertAdapter"),
    "QualityVerificationAdapter": (".quality_verification_adapter", "QualityVerificationAdapter"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module = import_module(target[0], __name__)
    value = getattr(module, target[1])
    globals()[name] = value
    return value

__all__ = [
    "ExpertAdapter",
    "ChangeDetectionAdapter",
    "ChangeDetectionInferenceEngine",
    "ExpertConfigurationError",
    "ExpertError",
    "ExpertHealth",
    "ExpertNotReadyError",
    "ExpertResult",
    "ExpertRuntimeError",
    "ExpertRuntime",
    "GeometryRelationAdapter",
    "GufnetInferenceEngine",
    "HydroProgram3DAdapter",
    "HydroProgram3DInferenceEngine",
    "MultimodalGufnetAdapter",
    "PointGufnetAdapter",
    "PointceptPtv3Adapter",
    "PointceptPtv3InferenceEngine",
    "MockExpertAdapter",
    "QualityVerificationAdapter",
    "build_mock_runtime",
    "build_remote_runtime",
    "overlay_remote_tools",
    "load_expert_runtime",
    "RemoteExpertAdapter",
    "RemoteExpertError",
]

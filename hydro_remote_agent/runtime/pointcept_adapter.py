from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np

from .adapter import ExpertAdapter
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, normalize_arguments
from .gufnet_adapter import WCS_CLASS_NAMES
from .pointcept_engine import PointceptEnginePool, PointceptPrediction, PointceptPtv3InferenceEngine


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PointceptPtv3Adapter(ExpertAdapter):
    def __init__(
        self,
        *args: Any,
        checkpoint_path: str | Path,
        config_path: str | Path,
        vendor_root: str | Path,
        backend_name: str = "pointcept_ptv3_inference",
        model_family: str = "PointTransformerV3",
        device: str = "cuda:0",
        split: str = "test",
        split_root: str | Path | None = None,
        python_paths: Sequence[str | Path] = (),
        prediction_cache_dir: str | Path | None = None,
        prediction_write_cache_dir: str | Path | None = None,
        cache_labels_zero_based: bool = True,
        engine: Optional[PointceptPtv3InferenceEngine] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, backend=backend_name, **kwargs)
        self.checkpoint_path = Path(checkpoint_path)
        self.config_path = Path(config_path)
        self.vendor_root = Path(vendor_root)
        self.model_family = str(model_family)
        self.device = device
        self.split = split
        self.split_root = Path(split_root) if split_root is not None else None
        self.python_paths = tuple(Path(path) for path in python_paths)
        self.prediction_cache_dir = (
            Path(prediction_cache_dir) if prediction_cache_dir is not None else None
        )
        self.prediction_write_cache_dir = (
            Path(prediction_write_cache_dir)
            if prediction_write_cache_dir is not None
            else None
        )
        self.cache_labels_zero_based = cache_labels_zero_based
        self._prepared = False
        self.engine = engine or PointceptEnginePool.get(
            self.checkpoint_path,
            self.config_path,
            self.vendor_root,
            self.device,
            self.split,
            self.split_root,
            self.python_paths,
        )

    def prepare(self) -> ExpertHealth:
        if self.enabled:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            if self.prediction_cache_dir is not None:
                if not self.prediction_cache_dir.is_dir():
                    raise FileNotFoundError(
                        f"Missing Pointcept prediction cache: {self.prediction_cache_dir}"
                    )
            else:
                self.engine.prepare()
            if self.prediction_write_cache_dir is not None:
                self.prediction_write_cache_dir.mkdir(parents=True, exist_ok=True)
            self._prepared = True
        return self.health_check()

    def health_check(self) -> ExpertHealth:
        if not self.enabled:
            return ExpertHealth(
                tool=self.tool_spec.name,
                backend=self.backend,
                status="disabled",
                initialized=False,
                message="Expert is disabled by runtime configuration.",
            )
        ready = self._prepared and (
            self.prediction_cache_dir is not None or self.engine.initialized
        )
        return ExpertHealth(
            tool=self.tool_spec.name,
            backend=self.backend,
            status="ready" if ready else "not_ready",
            initialized=ready,
            message="Pointcept semantic engine is ready." if ready else "Pointcept semantic engine is not prepared.",
            details={
                "is_mock": False,
                "checkpoint": str(self.checkpoint_path),
                "config": str(self.config_path),
                "device": self.device,
                "split": self.split,
                "split_root": str(self.split_root) if self.split_root is not None else None,
                "python_paths": [str(path) for path in self.python_paths],
                "training_modalities": ["point_cloud"],
                "inference_modalities": ["point_cloud"],
                "model_family": self.model_family,
                "original_point_replay": True,
                "prediction_cache_dir": (
                    str(self.prediction_cache_dir)
                    if self.prediction_cache_dir is not None
                    else None
                ),
                "prediction_write_cache_dir": (
                    str(self.prediction_write_cache_dir)
                    if self.prediction_write_cache_dir is not None
                    else None
                ),
            },
        )

    def _cached_prediction(self, point_cloud_path: str | Path) -> Optional[PointceptPrediction]:
        if self.prediction_cache_dir is None and self.prediction_write_cache_dir is None:
            return None
        sample_id = PointceptPtv3InferenceEngine.sample_id_from_path(point_cloud_path)
        cache_paths = [
            root / f"{sample_id}_pred.npy"
            for root in (self.prediction_write_cache_dir, self.prediction_cache_dir)
            if root is not None
        ]
        cache_path = next((path for path in cache_paths if path.is_file()), None)
        if cache_path is None:
            return None
        labels = np.asarray(np.load(cache_path, allow_pickle=False)).reshape(-1)
        if not np.issubdtype(labels.dtype, np.integer):
            raise ValueError(f"Cached Pointcept labels must be integers: {cache_path}")
        labels = labels.astype(np.int32, copy=False)
        if self.cache_labels_zero_based:
            labels = labels + 1
        if labels.size and (int(labels.min()) < 1 or int(labels.max()) > 15):
            raise ValueError(f"Cached Pointcept labels must be in raw class range 1..15: {cache_path}")
        source_count = int(np.loadtxt(point_cloud_path, usecols=(0,), ndmin=1).shape[0])
        if len(labels) != source_count:
            raise ValueError(
                f"{sample_id}: cached prediction contains {len(labels)} labels for "
                f"{source_count} source points: {cache_path}"
            )
        probabilities = np.zeros((len(labels), 15), dtype=np.float32)
        if len(labels):
            probabilities[np.arange(len(labels)), labels - 1] = 1.0
        return PointceptPrediction(
            point_labels=labels,
            class_probabilities=probabilities,
            num_points=len(labels),
            device="prediction_cache",
            sample_id=sample_id,
            checkpoint_epoch=-1,
        )

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if not self.enabled or not self._prepared:
            raise ExpertNotReadyError(f"Expert {self.tool_spec.name!r} is not ready")
        normalized_arguments = normalize_arguments(arguments)
        started_at = _utc_now()
        started = time.perf_counter()
        prediction = self._cached_prediction(normalized_arguments["point_cloud_path"])
        if prediction is None:
            prediction = self.engine.predict(normalized_arguments["point_cloud_path"])
            if self.prediction_write_cache_dir is not None:
                cache_labels = (
                    prediction.point_labels - 1
                    if self.cache_labels_zero_based
                    else prediction.point_labels
                )
                np.save(
                    self.prediction_write_cache_dir / f"{prediction.sample_id}_pred.npy",
                    cache_labels.astype(np.int32, copy=False),
                    allow_pickle=False,
                )
        invocation_dir = self.work_dir / invocation_id
        invocation_dir.mkdir(parents=True, exist_ok=False)

        labels_path = invocation_dir / "point_labels.npz"
        np.savez_compressed(
            labels_path,
            point_labels=prediction.point_labels,
            label_space=np.asarray("raw_class_id_1_to_15"),
        )
        probabilities_path = invocation_dir / "class_probabilities.npz"
        np.savez_compressed(
            probabilities_path,
            class_probabilities=prediction.class_probabilities,
            class_ids=np.arange(1, 16, dtype=np.int32),
        )
        requested_ids = normalized_arguments.get("target_class_ids")
        class_ids = [int(value) for value in requested_ids] if requested_ids else list(range(1, 16))
        masks_path = invocation_dir / "class_masks.npz"
        np.savez_compressed(
            masks_path,
            class_ids=np.asarray(class_ids, dtype=np.int32),
            class_masks=np.stack(
                [prediction.point_labels == class_id for class_id in class_ids], axis=0
            ),
        )

        classes = []
        for class_id in np.unique(prediction.point_labels):
            class_id = int(class_id)
            mask = prediction.point_labels == class_id
            classes.append(
                {
                    "class_id": class_id,
                    "class_name": WCS_CLASS_NAMES[class_id - 1],
                    "point_count": int(mask.sum()),
                    "point_ratio": float(mask.mean()),
                    "mean_confidence": float(
                        prediction.class_probabilities[mask, class_id - 1].mean()
                    ),
                }
            )
        classes.sort(key=lambda item: item["point_count"], reverse=True)
        summary_path = invocation_dir / "class_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "sample_id": prediction.sample_id,
                    "num_points": prediction.num_points,
                    "num_present_classes": len(classes),
                    "classes": classes,
                    "dominant_class": classes[0] if classes else None,
                    "model_family": self.model_family,
                    "original_point_replay": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        artifacts: Dict[str, str] = {
            "point_labels": str(labels_path.resolve()),
            "class_masks": str(masks_path.resolve()),
            "class_probabilities": str(probabilities_path.resolve()),
            "class_summary": str(summary_path.resolve()),
        }
        manifest_path = invocation_dir / "manifest.json"
        result = ExpertResult(
            schema_version="1.0",
            invocation_id=invocation_id,
            tool=self.tool_spec.name,
            tool_version=self.tool_spec.version,
            backend=self.backend,
            status="succeeded",
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            coordinate_space=self.tool_spec.output.coordinate_space,
            result_types=self.tool_spec.output.result_types,
            artifacts=artifacts,
            manifest_path=str(manifest_path.resolve()),
            arguments=normalized_arguments,
            is_mock=False,
            metrics={
                "num_points": prediction.num_points,
                "num_present_classes": len(classes),
                "device": prediction.device,
                "sample_id": prediction.sample_id,
                "checkpoint_epoch": prediction.checkpoint_epoch,
                "original_point_replay": True,
                "prediction_source": (
                    "cache" if prediction.device == "prediction_cache" else "online_inference"
                ),
                "model_family": self.model_family,
            },
        )
        result.write_manifest()
        return result

    def shutdown(self) -> None:
        return None

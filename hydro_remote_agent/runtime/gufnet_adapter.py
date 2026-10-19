from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import numpy as np

from .adapter import ExpertAdapter
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, normalize_arguments
from .gufnet_engine import GufnetEnginePool, GufnetInferenceEngine


WCS_CLASS_NAMES = (
    "简易棚屋", "混凝土房屋", "水泥道路", "土路", "边坡", "陡坎", "坝体",
    "菜地", "草地", "旱地", "林地", "裸地", "水岸线", "沟渠", "其他",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GufnetSegmentationAdapter(ExpertAdapter):
    """GUFNet multi-modal-trained, point-only-inference segmentation adapter."""

    def __init__(
        self,
        *args: Any,
        checkpoint_path: str | Path,
        config_path: str | Path,
        vendor_root: str | Path,
        device: str = "cuda:0",
        max_chunk_points: int = 100_000,
        min_chunk_points: int = 12_500,
        accepts_image: bool = False,
        engine: Optional[GufnetInferenceEngine] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, backend="gufnet_3d_inference", **kwargs)
        self.checkpoint_path = Path(checkpoint_path)
        self.config_path = Path(config_path)
        self.vendor_root = Path(vendor_root)
        self.device = device
        self.accepts_image = accepts_image
        self.engine = engine or GufnetEnginePool.get(
            checkpoint_path=self.checkpoint_path,
            config_path=self.config_path,
            vendor_root=self.vendor_root,
            device=self.device,
            max_chunk_points=max_chunk_points,
            min_chunk_points=min_chunk_points,
        )

    def prepare(self) -> ExpertHealth:
        if not self.enabled:
            return self.health_check()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.engine.prepare()
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
        ready = self.engine.initialized
        return ExpertHealth(
            tool=self.tool_spec.name,
            backend=self.backend,
            status="ready" if ready else "not_ready",
            initialized=ready,
            message=(
                "Shared GUFNet point-inference engine is ready."
                if ready
                else "Shared GUFNet engine has not been prepared."
            ),
            details={
                "is_mock": False,
                "checkpoint": str(self.checkpoint_path),
                "device": self.device,
                "training_modalities": ["image", "point_cloud"],
                "inference_modalities": ["point_cloud"],
                "image_used": False,
                "max_chunk_points": self.engine.max_chunk_points,
                "min_chunk_points": self.engine.min_chunk_points,
            },
        )

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if not self.enabled or not self.engine.initialized:
            raise ExpertNotReadyError(f"Expert {self.tool_spec.name!r} is not ready")
        normalized_arguments = normalize_arguments(arguments)
        if self.accepts_image:
            image_path = Path(normalized_arguments["image_path"])
            if not image_path.is_file():
                raise FileNotFoundError(f"Missing image: {image_path}")

        started_at = _utc_now()
        started = time.perf_counter()
        prediction = self.engine.predict(normalized_arguments["point_cloud_path"])
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
        masks = np.stack(
            [prediction.point_labels == class_id for class_id in class_ids], axis=0
        )
        masks_path = invocation_dir / "class_masks.npz"
        np.savez_compressed(
            masks_path,
            class_ids=np.asarray(class_ids, dtype=np.int32),
            class_masks=masks,
        )

        class_summary_path = invocation_dir / "class_summary.json"
        classes = []
        for class_id in np.unique(prediction.point_labels):
            class_id = int(class_id)
            class_mask = prediction.point_labels == class_id
            count = int(class_mask.sum())
            confidence = None
            if 1 <= class_id <= prediction.class_probabilities.shape[1] and count:
                confidence = float(prediction.class_probabilities[class_mask, class_id - 1].mean())
            classes.append(
                {
                    "class_id": class_id,
                    "class_name": WCS_CLASS_NAMES[class_id - 1] if 1 <= class_id <= len(WCS_CLASS_NAMES) else f"类别 {class_id}",
                    "point_count": count,
                    "point_ratio": float(count / max(prediction.num_points, 1)),
                    "mean_confidence": confidence,
                }
            )
        classes.sort(key=lambda item: item["point_count"], reverse=True)
        class_summary_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "num_points": prediction.num_points,
                    "num_present_classes": len(classes),
                    "classes": classes,
                    "dominant_class": classes[0] if classes else None,
                    "inference_mode": "point_only",
                    "image_validated": self.accepts_image,
                    "image_used": False,
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
            "class_summary": str(class_summary_path.resolve()),
        }
        if "projection_metadata" in self.tool_spec.output.artifacts:
            projection_path = invocation_dir / "projection_metadata.json"
            with projection_path.open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema_version": "1.0",
                        "image_path": normalized_arguments.get("image_path"),
                        "image_used": False,
                        "reason": "GUFNet uses image supervision during training and point-only inference.",
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
            artifacts["projection_metadata"] = str(projection_path.resolve())

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
                "num_present_classes": int(len(np.unique(prediction.point_labels))),
                "device": prediction.device,
                "image_used": False,
                "max_chunk_points": self.engine.max_chunk_points,
            },
            warnings=(
                "Image input was validated but not used during GUFNet inference."
                if self.accepts_image
                else "GUFNet was multi-modal trained and uses point-only inference.",
            ),
        )
        result.write_manifest()
        return result

    def shutdown(self) -> None:
        # The engine is process-shared; lifecycle ownership remains with the pool.
        return None


class PointGufnetAdapter(GufnetSegmentationAdapter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, accepts_image=False, **kwargs)


class MultimodalGufnetAdapter(GufnetSegmentationAdapter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, accepts_image=True, **kwargs)

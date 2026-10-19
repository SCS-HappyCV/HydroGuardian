from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np
from PIL import Image

from .adapter import ExpertAdapter
from .change_detection_engine import (
    ChangeDetectionEnginePool,
    ChangeDetectionInferenceEngine,
)
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, normalize_arguments


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_change_regions(
    probability_map: np.ndarray,
    threshold: float,
    minimum_region_pixels: int,
) -> Tuple[np.ndarray, list[Dict[str, Any]]]:
    initial_mask = np.asarray(probability_map >= threshold, dtype=bool)
    try:
        import cv2
    except ImportError:
        return _extract_change_regions_numpy(
            probability_map, initial_mask, minimum_region_pixels
        )
    component_count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        initial_mask.astype(np.uint8), connectivity=8
    )
    filtered_mask = np.zeros_like(initial_mask)
    regions = []
    for component_id in range(1, component_count):
        area = int(stats[component_id, cv2.CC_STAT_AREA])
        if area < minimum_region_pixels:
            continue
        component_mask = labels == component_id
        filtered_mask[component_mask] = True
        component_probabilities = probability_map[component_mask]
        regions.append(
            {
                "region_id": len(regions) + 1,
                "area_pixels": area,
                "bbox_xywh": [
                    int(stats[component_id, cv2.CC_STAT_LEFT]),
                    int(stats[component_id, cv2.CC_STAT_TOP]),
                    int(stats[component_id, cv2.CC_STAT_WIDTH]),
                    int(stats[component_id, cv2.CC_STAT_HEIGHT]),
                ],
                "centroid_xy": [float(value) for value in centroids[component_id]],
                "mean_probability": float(component_probabilities.mean()),
                "maximum_probability": float(component_probabilities.max()),
            }
        )
    return filtered_mask, regions


def _extract_change_regions_numpy(
    probability_map: np.ndarray,
    initial_mask: np.ndarray,
    minimum_region_pixels: int,
) -> Tuple[np.ndarray, list[Dict[str, Any]]]:
    height, width = initial_mask.shape
    visited = np.zeros_like(initial_mask)
    filtered_mask = np.zeros_like(initial_mask)
    regions = []
    for start_y, start_x in np.argwhere(initial_mask):
        if visited[start_y, start_x]:
            continue
        stack = [(int(start_y), int(start_x))]
        visited[start_y, start_x] = True
        pixels = []
        while stack:
            pixel_y, pixel_x = stack.pop()
            pixels.append((pixel_y, pixel_x))
            for offset_y in (-1, 0, 1):
                for offset_x in (-1, 0, 1):
                    if offset_y == 0 and offset_x == 0:
                        continue
                    neighbor_y = pixel_y + offset_y
                    neighbor_x = pixel_x + offset_x
                    if (
                        0 <= neighbor_y < height
                        and 0 <= neighbor_x < width
                        and initial_mask[neighbor_y, neighbor_x]
                        and not visited[neighbor_y, neighbor_x]
                    ):
                        visited[neighbor_y, neighbor_x] = True
                        stack.append((neighbor_y, neighbor_x))
        if len(pixels) < minimum_region_pixels:
            continue
        coordinates = np.asarray(pixels, dtype=np.int32)
        rows, columns = coordinates[:, 0], coordinates[:, 1]
        filtered_mask[rows, columns] = True
        component_probabilities = probability_map[rows, columns]
        minimum_x, maximum_x = int(columns.min()), int(columns.max())
        minimum_y, maximum_y = int(rows.min()), int(rows.max())
        regions.append(
            {
                "region_id": len(regions) + 1,
                "area_pixels": len(pixels),
                "bbox_xywh": [
                    minimum_x,
                    minimum_y,
                    maximum_x - minimum_x + 1,
                    maximum_y - minimum_y + 1,
                ],
                "centroid_xy": [float(columns.mean()), float(rows.mean())],
                "mean_probability": float(component_probabilities.mean()),
                "maximum_probability": float(component_probabilities.max()),
            }
        )
    return filtered_mask, regions


class ChangeDetectionAdapter(ExpertAdapter):
    def __init__(
        self,
        *args: Any,
        checkpoint_path: str | Path,
        vendor_root: str | Path,
        device: str = "cuda:0",
        input_size: int = 256,
        engine: Optional[ChangeDetectionInferenceEngine] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, backend="rfanet_change_detection", **kwargs)
        self.checkpoint_path = Path(checkpoint_path)
        self.vendor_root = Path(vendor_root)
        self.device = device
        self.input_size = int(input_size)
        self.engine = engine or ChangeDetectionEnginePool.get(
            checkpoint_path=self.checkpoint_path,
            vendor_root=self.vendor_root,
            device=self.device,
            input_size=self.input_size,
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
            message="RFANet change-detection engine is ready." if ready else "RFANet is not prepared.",
            details={
                "is_mock": False,
                "checkpoint": str(self.checkpoint_path),
                "device": self.device,
                "input_size": self.input_size,
                "checkpoint_load": getattr(
                    self.engine,
                    "load_report",
                    {"missing_keys": (), "unexpected_keys": ()},
                ),
            },
        )

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if not self.enabled or not self.engine.initialized:
            raise ExpertNotReadyError(f"Expert {self.tool_spec.name!r} is not ready")
        normalized = normalize_arguments(arguments)
        started_at = _utc_now()
        started = time.perf_counter()
        prediction = self.engine.predict(
            normalized["before_image_path"], normalized["after_image_path"]
        )
        threshold = float(normalized.get("change_threshold", 0.0005))
        minimum_pixels = int(normalized.get("minimum_region_pixels", 0))
        change_mask, regions = extract_change_regions(
            prediction.probability_map, threshold, minimum_pixels
        )

        invocation_dir = self.work_dir / invocation_id
        invocation_dir.mkdir(parents=True, exist_ok=False)
        mask_path = invocation_dir / "change_mask.png"
        Image.fromarray(change_mask.astype(np.uint8) * 255, mode="L").save(mask_path)
        probability_path = invocation_dir / "change_probability_map.npz"
        np.savez_compressed(
            probability_path,
            change_probability_map=prediction.probability_map,
            coordinate_space=np.asarray("after_image_pixels"),
        )
        regions_path = invocation_dir / "change_regions.json"
        region_payload = {
            "schema_version": "1.0",
            "image_size_hw": list(prediction.original_size),
            "threshold": threshold,
            "minimum_region_pixels": minimum_pixels,
            "changed_pixels": int(change_mask.sum()),
            "changed_ratio": float(change_mask.mean()),
            "regions": regions,
        }
        regions_path.write_text(
            json.dumps(region_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

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
            artifacts={
                "change_mask": str(mask_path.resolve()),
                "change_probability_map": str(probability_path.resolve()),
                "change_regions": str(regions_path.resolve()),
            },
            manifest_path=str(manifest_path.resolve()),
            arguments=normalized,
            is_mock=False,
            metrics={
                "image_height": prediction.original_size[0],
                "image_width": prediction.original_size[1],
                "changed_pixels": int(change_mask.sum()),
                "changed_ratio": float(change_mask.mean()),
                "region_count": len(regions),
                "device": prediction.device,
            },
            warnings=(),
        )
        result.write_manifest()
        return result

    def shutdown(self) -> None:
        return None

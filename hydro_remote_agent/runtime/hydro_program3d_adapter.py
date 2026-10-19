from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np

from .adapter import ExpertAdapter
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, normalize_arguments
from .hydro_program3d_engine import (
    HydroProgram3DEnginePool,
    HydroProgram3DInferenceEngine,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HydroProgram3DAdapter(ExpertAdapter):
    def __init__(
        self,
        *args: Any,
        checkpoint_path: str | Path,
        device: str = "cuda:0",
        geometry_root: str | Path | None = None,
        geometry_split: str = "test",
        max_points: int | None = None,
        image_size: int | None = None,
        mask_threshold: float = 0.5,
        mask_thresholds: Mapping[str, float] | None = None,
        no_target_posterior_threshold: float | None = None,
        no_target_probability_max_threshold: float | None = None,
        compiler_backend: str = "rule",
        engine: Optional[HydroProgram3DInferenceEngine] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, backend="hydro_program3d_inference", **kwargs)
        self.checkpoint_path = Path(checkpoint_path)
        self.device = str(device)
        self.engine = engine or HydroProgram3DEnginePool.get(
            checkpoint_path=self.checkpoint_path,
            device=self.device,
            geometry_root=geometry_root,
            geometry_split=geometry_split,
            max_points=max_points,
            image_size=image_size,
            mask_threshold=mask_threshold,
            mask_thresholds=dict(mask_thresholds or {}),
            no_target_posterior_threshold=no_target_posterior_threshold,
            no_target_probability_max_threshold=no_target_probability_max_threshold,
            compiler_backend=compiler_backend,
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
                self.tool_spec.name, self.backend, "disabled", False,
                "Expert is disabled by runtime configuration."
            )
        ready = self.engine.initialized
        return ExpertHealth(
            self.tool_spec.name,
            self.backend,
            "ready" if ready else "not_ready",
            ready,
            "HydroProgram3D language expert is ready." if ready else "HydroProgram3D engine has not been prepared.",
            {
                "is_mock": False,
                "checkpoint": str(self.checkpoint_path),
                "device": self.device,
                "source_coordinate_output": True,
            },
        )

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if not self.enabled or not self.engine.initialized:
            raise ExpertNotReadyError(f"Expert {self.tool_spec.name!r} is not ready")
        normalized = normalize_arguments(arguments)
        started_at = _utc_now()
        started = time.perf_counter()
        prediction = self.engine.predict(
            normalized["image_path"],
            normalized["point_cloud_path"],
            normalized["query"],
        )
        invocation_dir = self.work_dir / invocation_id
        invocation_dir.mkdir(parents=True, exist_ok=False)

        mask_path = invocation_dir / "target_mask.npz"
        np.savez_compressed(mask_path, target_mask=prediction.target_mask)
        probabilities_path = invocation_dir / "target_probabilities.npz"
        np.savez_compressed(
            probabilities_path,
            target_probabilities=prediction.target_probabilities,
        )
        preview_path = invocation_dir / "point_visualization.npz"
        preview_indices = prediction.preview_indices
        if preview_indices is None:
            preview_indices = np.arange(prediction.num_source_points, dtype=np.uint32)
        preview_positions = prediction.preview_positions
        if preview_positions is None:
            preview_positions = np.zeros((len(preview_indices), 3), dtype=np.float32)
        preview_colors = prediction.preview_colors
        if preview_colors is None:
            preview_colors = np.full((len(preview_indices), 3), 180, dtype=np.uint8)
        preview_bounds = prediction.preview_bounds
        if preview_bounds is None:
            preview_bounds = np.asarray([
                preview_positions[:, 0].min(initial=0), preview_positions[:, 1].min(initial=0), preview_positions[:, 2].min(initial=0),
                preview_positions[:, 0].max(initial=0), preview_positions[:, 1].max(initial=0), preview_positions[:, 2].max(initial=0),
            ], dtype=np.float64)
        np.savez_compressed(
            preview_path,
            positions=preview_positions,
            colors=preview_colors,
            target_mask=prediction.target_mask[preview_indices],
            target_probabilities=prediction.target_probabilities[preview_indices],
            source_indices=preview_indices,
            source_bounds=preview_bounds,
            num_source_points=np.asarray([prediction.num_source_points], dtype=np.uint32),
        )
        sampling_path = invocation_dir / "sampling_metadata.json"
        sampling_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "method": "deterministic_uniform_sample_then_nearest_neighbor",
                    "num_source_points": prediction.num_source_points,
                    "num_sampled_points": prediction.num_sampled_points,
                    "sample_indices": prediction.sample_indices.tolist(),
                    "output_coordinate_space": "source_point_cloud",
                    "geometry_used": prediction.geometry_used,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        program_path = invocation_dir / "compiled_program.json"
        program_path.write_text(
            json.dumps(
                {
                    "query": normalized["query"],
                    "program_bundle": prediction.compiled_program,
                    "selected_program": prediction.selected_program,
                    "inference_diagnostics": {
                        "selected_candidate_index": prediction.selected_candidate_index,
                        "candidate_posterior_scores": list(prediction.candidate_posterior_scores),
                        "candidate_active_mask": list(prediction.candidate_active_mask),
                        "posterior_no_target_mass": prediction.posterior_no_target_mass,
                        "abstain_probability": prediction.abstain_probability,
                        "inferred_task_type": prediction.inferred_task_type,
                        "applied_mask_threshold": prediction.applied_mask_threshold,
                        "model_no_target": prediction.model_no_target,
                        "calibrated_no_target": prediction.calibrated_no_target,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        artifacts = {
            "target_mask": str(mask_path.resolve()),
            "target_probabilities": str(probabilities_path.resolve()),
            "sampling_metadata": str(sampling_path.resolve()),
            "compiled_program": str(program_path.resolve()),
            "point_visualization": str(preview_path.resolve()),
        }
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
            manifest_path=str((invocation_dir / "manifest.json").resolve()),
            arguments=normalized,
            is_mock=False,
            metrics={
                "num_points": prediction.num_source_points,
                "num_sampled_points": prediction.num_sampled_points,
                "selected_points": int(prediction.target_mask.sum()),
                "selected_ratio": float(prediction.target_mask.mean()),
                "execution_confidence": prediction.execution_confidence,
                "abstain_probability": prediction.abstain_probability,
                "abstained": prediction.abstained,
                "no_target": prediction.no_target,
                "selected_candidate_index": prediction.selected_candidate_index,
                "candidate_posterior_scores": list(prediction.candidate_posterior_scores),
                "posterior_no_target_mass": prediction.posterior_no_target_mass,
                "inferred_task_type": prediction.inferred_task_type,
                "applied_mask_threshold": prediction.applied_mask_threshold,
                "model_no_target": prediction.model_no_target,
                "calibrated_no_target": prediction.calibrated_no_target,
                "probability_mean": float(prediction.target_probabilities.mean()),
                "probability_p99": float(np.quantile(prediction.target_probabilities, 0.99)),
                "probability_max": float(prediction.target_probabilities.max()),
                "device": prediction.device,
                "geometry_used": prediction.geometry_used,
            },
            warnings=("Model abstained from this request.",) if prediction.abstained else (),
        )
        result.write_manifest()
        return result

    def shutdown(self) -> None:
        self.engine.shutdown()

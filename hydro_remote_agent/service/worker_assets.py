from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from .assets import ArtifactRecord, MinioAssetStore
from .spatial import SPATIAL_CONTEXT_SCHEMA_VERSION, enrich_pixel_regions, inspect_spatial_asset


class WorkerAssetManager:
    def __init__(self, store: MinioAssetStore, work_dir: str | Path) -> None:
        self.store = store
        self.work_dir = Path(work_dir)
        self._spatial_by_task: dict[str, dict[str, dict[str, Any]]] = {}

    def materialize(self, value: Any, task_id: str, role: str = "asset") -> Any:
        if isinstance(value, dict) and set(value) == {"$artifact"}:
            payload = value["$artifact"]
            if not isinstance(payload, dict):
                raise ValueError("$artifact must contain an object")
            record = ArtifactRecord(**payload)
            filename = Path(record.object_key).name
            target = self.work_dir / task_id / "inputs" / record.artifact_id / filename
            resolved = self.store.download(record, target).resolve()
            inherited = record.metadata.get("spatial") if isinstance(record.metadata, dict) else None
            spatial = inspect_spatial_asset(resolved, role, inherited if isinstance(inherited, dict) else None)
            if spatial:
                self._spatial_by_task.setdefault(task_id, {})[role] = spatial
            return str(resolved)
        if isinstance(value, dict):
            return {key: self.materialize(child, task_id, str(key)) for key, child in value.items()}
        if isinstance(value, list):
            return [self.materialize(child, task_id, role) for child in value]
        return value

    def cleanup(self, task_id: str) -> None:
        shutil.rmtree(self.work_dir / task_id, ignore_errors=True)
        self._spatial_by_task.pop(task_id, None)

    def _spatial_context(self, task_id: str) -> dict[str, Any]:
        assets = dict(self._spatial_by_task.get(task_id, {}))
        primary = next((assets[name] for name in ("after_image_path", "image_path", "point_cloud_path", "before_image_path") if name in assets), None)
        return {
            "schema_version": SPATIAL_CONTEXT_SCHEMA_VERSION,
            "assets": assets,
            "primary": primary or next(iter(assets.values()), None),
        } if assets else {}

    @staticmethod
    def _output_spatial(role: str, context: dict[str, Any]) -> Optional[dict[str, Any]]:
        assets = context.get("assets", {})
        if not isinstance(assets, dict):
            return None
        if role in {"change_mask", "change_probability_map", "change_regions", "diagnostic_overlay"}:
            return assets.get("after_image_path") or assets.get("image_path")
        if role in {"point_labels", "class_masks", "class_probabilities", "target_mask", "target_probabilities", "point_visualization", "relation_mask", "geometry_report"}:
            return assets.get("point_cloud_path")
        return context.get("primary") if isinstance(context.get("primary"), dict) else None

    def _enrich_spatial_reports(self, artifacts: dict[str, Any], context: dict[str, Any]) -> None:
        regions_path = artifacts.get("change_regions")
        spatial = self._output_spatial("change_regions", context)
        if not isinstance(regions_path, str) or not isinstance(spatial, dict) or not Path(regions_path).is_file():
            return
        path = Path(regions_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            path.write_text(json.dumps(enrich_pixel_regions(payload, spatial), ensure_ascii=False, indent=2), encoding="utf-8")

    def publish_result(
        self,
        result: dict[str, Any],
        task_id: str,
        job_id: str,
        source_arguments: Any = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        published = dict(result)
        if source_arguments is not None:
            published["arguments"] = self.stable_references(source_arguments)
        artifacts = result.get("artifacts")
        spatial_context = self._spatial_context(task_id)
        if spatial_context:
            published["spatial_context"] = spatial_context
        records: list[dict[str, Any]] = []
        if not isinstance(artifacts, dict):
            return published, records
        self._enrich_spatial_reports(artifacts, spatial_context)
        resolved: dict[str, str] = {}
        for name, value in artifacts.items():
            if not isinstance(value, str):
                continue
            path = Path(value)
            if not path.is_file():
                resolved[name] = value
                continue
            spatial = self._output_spatial(name, spatial_context)
            record = self.store.upload(
                path, job_id=job_id or "jobs", step_id=task_id, name=path.name,
                metadata={"spatial": spatial, "spatial_role": name} if spatial else None,
            )
            records.append(record.to_dict())
            resolved[name] = f"artifact://{record.artifact_id}"
        published["artifacts"] = resolved
        manifest_value = result.get("manifest_path")
        if isinstance(manifest_value, str) and Path(manifest_value).is_file():
            manifest_path = Path(manifest_value)
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(manifest_payload, dict):
                manifest_payload["artifacts"] = resolved
                if source_arguments is not None:
                    manifest_payload["arguments"] = published["arguments"]
                if spatial_context:
                    manifest_payload["spatial_context"] = spatial_context
                manifest_path.write_text(
                    json.dumps(manifest_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            manifest = self.store.upload(
                manifest_value, job_id=job_id or "jobs", step_id=task_id, name="manifest.json",
                metadata={"spatial_context": spatial_context} if spatial_context else None,
            )
            records.append(manifest.to_dict())
            published["manifest_path"] = f"artifact://{manifest.artifact_id}"
        return published, records

    @classmethod
    def stable_references(cls, value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"$artifact"}:
            payload = value["$artifact"]
            if isinstance(payload, dict) and isinstance(payload.get("artifact_id"), str):
                return f"artifact://{payload['artifact_id']}"
        if isinstance(value, dict):
            return {key: cls.stable_references(child) for key, child in value.items()}
        if isinstance(value, list):
            return [cls.stable_references(child) for child in value]
        return value

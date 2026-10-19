from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.service.assets import (
    ArtifactCatalog,
    ArtifactRecord,
    artifact_id_from_uri,
    file_sha256,
    resolve_artifact_references,
)
from hydro_remote_agent.service.worker_assets import WorkerAssetManager


class _AssetStore:
    def __init__(self, source: Path, output: Path) -> None:
        self.source = source
        self.output = output

    def download(self, record: ArtifactRecord, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.source.read_bytes())
        return target

    def upload(self, source, **_):
        path = Path(source)
        self.output.write_bytes(path.read_bytes())
        return ArtifactRecord(
            artifact_id="art_output",
            bucket="hydro-output",
            object_key=f"jobs/{path.name}",
            media_type="application/octet-stream",
            size_bytes=path.stat().st_size,
            sha256=file_sha256(path),
            metadata={},
        )


class AssetProtocolTest(unittest.TestCase):
    def test_catalog_resolves_artifact_uri(self) -> None:
        catalog = ArtifactCatalog()
        record = ArtifactRecord(
            artifact_id="art_input",
            bucket="hydro-input",
            object_key="default/job/input/art_input/tile.txt",
            media_type="text/plain",
            size_bytes=4,
            sha256=None,
            metadata={"tile_id": "tile"},
        )
        catalog.put(record)
        resolved = resolve_artifact_references(
            {"point_cloud_path": "artifact://art_input", "query": "water"}, catalog
        )
        self.assertEqual(resolved["point_cloud_path"]["$artifact"]["object_key"], record.object_key)
        self.assertEqual(artifact_id_from_uri("artifact://art_input"), "art_input")

    def test_worker_materializes_and_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.txt"
            source.write_text("points", encoding="utf-8")
            output = root / "uploaded.txt"
            manager = WorkerAssetManager(_AssetStore(source, output), root / "work")
            source_reference = {"$artifact": {
                "artifact_id": "art_input", "bucket": "hydro-input",
                "object_key": "input/tile.txt", "media_type": "text/plain",
                "size_bytes": source.stat().st_size, "sha256": file_sha256(source), "metadata": {},
            }}
            local_path = manager.materialize(source_reference, "task-1")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({
                "artifacts": {"point_labels": local_path},
                "arguments": {"point_cloud_path": local_path},
            }), encoding="utf-8")
            result, records = manager.publish_result(
                {"artifacts": {"point_labels": local_path}, "manifest_path": str(manifest_path)},
                "task-1", "job-1", {"point_cloud_path": source_reference},
            )
            self.assertEqual(result["artifacts"]["point_labels"], "artifact://art_output")
            self.assertEqual(result["arguments"]["point_cloud_path"], "artifact://art_input")
            self.assertEqual(records[0]["artifact_id"], "art_output")
            published_manifest = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(published_manifest["artifacts"]["point_labels"], "artifact://art_output")
            self.assertEqual(published_manifest["arguments"]["point_cloud_path"], "artifact://art_input")
            manager.cleanup("task-1")
            self.assertFalse((root / "work" / "task-1").exists())


if __name__ == "__main__":
    unittest.main()

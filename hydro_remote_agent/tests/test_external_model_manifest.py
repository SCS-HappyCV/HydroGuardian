from __future__ import annotations

import json
from pathlib import Path

from hydro_remote_agent.tools.write_external_model_manifest import main


def test_write_external_model_manifest_supports_safetensors(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text("{}\n", encoding="utf-8")
    (model / "model-00001-of-00001.safetensors").write_bytes(b"weights")
    config = tmp_path / "external.json"
    config.write_text(
        json.dumps(
            {
                "model_id": "deepseek-ai/deepseek-vl2-small",
                "revision": "abc123",
                "source": "HuggingFace official repository",
            }
        ),
        encoding="utf-8",
    )
    assert main(["--config", str(config), "--model-path", str(model)]) == 0
    manifest = json.loads(
        (model / "vaguehydro_external_model_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["model_id"] == "deepseek-ai/deepseek-vl2-small"
    assert manifest["weight_shard_count"] == 1
    assert manifest["weight_shard_sha256"]

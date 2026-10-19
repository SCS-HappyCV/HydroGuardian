import json
from pathlib import Path

from hydro_remote_agent.tools.audit_expert_split_leakage import audit


def test_audit_detects_folder_based_overlap(tmp_path: Path) -> None:
    split = tmp_path / "test.jsonl"
    split.write_text(
        json.dumps({"folder_id": "00", "patch_id": "000004"}) + "\n"
        + json.dumps({"folder_id": "01", "patch_id": "000005"}) + "\n",
        encoding="utf-8",
    )
    legacy = tmp_path / "legacy"
    path = legacy / "00" / "velodyne" / "000004.pth"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"checkpoint input")
    result = audit(split, legacy, ["00", "01"])
    assert result["status"] == "leakage_detected"
    assert result["overlap_count"] == 1
    assert result["overlap_rate"] == 0.5

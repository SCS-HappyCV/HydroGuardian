from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from hydro_remote_agent.evaluation.routing import parse_json_response
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_single_jsonl(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError(f"{path} must contain exactly one JSON object")
    return rows[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the VagueHydro-R M0 LoRA smoke.")
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--prediction", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--expected-adapter", required=True)
    parser.add_argument("--split-name", required=True, choices=("val_sft",))
    parser.add_argument("--source-dataset", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    sample = read_single_jsonl(args.sample)
    prediction = read_single_jsonl(args.prediction)
    parsed = parse_json_response(prediction.get("prediction"))
    registry = load_tool_registry(args.registry)
    request = AgentRequest.from_dict(parsed, registry)
    inference = prediction.get("inference")
    inference = inference if isinstance(inference, dict) else {}
    checks = {
        "sample_prediction_id_match": str(sample.get("id", ""))
        == str(prediction.get("id", "")),
        "sample_split_is_validation": sample.get("split") == "val",
        "declared_split_is_val_sft": args.split_name == "val_sft",
        "source_dataset_exists": args.source_dataset.is_file(),
        "request_id_preserved": request.request_id == str(sample.get("id", "")),
        "backbone_revision": inference.get("revision") == args.expected_revision,
        "adapter_path": inference.get("adapter_path") == args.expected_adapter,
        "agent_request_valid": True,
    }
    status = "passed" if all(checks.values()) else "failed"
    report = {
        "schema_version": "vaguehydro_r.m0_lora_smoke.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "agent_request_valid": checks["agent_request_valid"],
        "sample_id": sample.get("id"),
        "split": {
            "name": args.split_name,
            "sample_field": sample.get("split"),
            "source_dataset": str(args.source_dataset),
            "source_dataset_sha256": sha256_file(args.source_dataset)
            if args.source_dataset.is_file()
            else None,
        },
        "sample_sha256": sha256_file(args.sample),
        "prediction_sha256": sha256_file(args.prediction),
        "prediction": prediction,
        "parsed_action_type": getattr(request.action, "type", None),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"VAGUEHYDRO_R_M0_SMOKE status={status} sample={sample.get('id')} "
        f"action={report['parsed_action_type']} output={args.output}"
    )
    return 0 if status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

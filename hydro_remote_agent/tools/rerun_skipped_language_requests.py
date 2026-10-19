from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerun requests previously skipped because the language expert was mock.")
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--previous-results", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--runtime", default=PROJECT_ROOT / "hydro_remote_agent/configs/expert_runtime.yaml")
    parser.add_argument("--registry", default=PROJECT_ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
    args = parser.parse_args()

    skipped_ids = {
        str(row["id"])
        for row in _read_jsonl(args.previous_results)
        if isinstance(row.get("result"), dict) and row["result"].get("execution_mode") == "skipped_mock"
    }
    selected = [row for row in _read_jsonl(args.predictions) if str(row.get("id")) in skipped_ids]
    if len(selected) != len(skipped_ids):
        raise ValueError(f"Matched {len(selected)} predictions for {len(skipped_ids)} skipped requests")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    subset_path = args.work_dir / "language_predictions.jsonl"
    subset_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in selected), encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "hydro_remote_agent.tools.evaluate_agent_execution",
        "--predictions", str(subset_path),
        "--output", str(args.work_dir / "execution_results.jsonl"),
        "--report", str(args.work_dir / "execution_report.json"),
        "--registry", str(args.registry),
        "--runtime", str(args.runtime),
        "--expert-work-dir", str(args.work_dir / "expert_outputs"),
        "--execution-work-dir", str(args.work_dir / "agent_executions"),
    ]
    print(f"LANGUAGE_RERUN_SELECTED count={len(selected)} subset={subset_path}", flush=True)
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

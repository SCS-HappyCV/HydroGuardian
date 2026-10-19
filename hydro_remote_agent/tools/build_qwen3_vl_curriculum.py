from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import read_jsonl
from hydro_remote_agent.training.curriculum import curriculum_report, select_curriculum, write_jsonl


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a balanced VagueHydro SFT curriculum.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    records = read_jsonl(Path(config["input_file"]))
    selected = select_curriculum(
        records,
        action_quotas=config["action_quotas"],
        seed=int(config["seed"]),
        max_records_per_tile=int(config["max_records_per_tile"]),
        max_parent_variants=config["max_parent_variants"],
    )
    output_path = Path(config["output_file"])
    write_jsonl(output_path, selected)
    report = curriculum_report(records, selected, config)
    report_path = Path(config["report_file"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"QWEN3_VL_CURRICULUM_OK records={len(selected)} fingerprint={report['dataset_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


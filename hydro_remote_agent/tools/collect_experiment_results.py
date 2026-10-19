from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydro_remote_agent.evaluation.experiment_ledger import (  # noqa: E402
    collect_experiment_ledger,
    write_experiment_ledger,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect immutable VagueHydro experiment reports.")
    parser.add_argument(
        "--protocol",
        type=Path,
        default=PROJECT_ROOT / "hydro_remote_agent/configs/experiment_protocol_v1.json",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "runs/hydro_remote_agent/experiments_v1",
    )
    args = parser.parse_args()
    ledger = collect_experiment_ledger(args.protocol, args.project_root)
    write_experiment_ledger(ledger, args.output_dir)
    print(json.dumps(ledger["status_counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

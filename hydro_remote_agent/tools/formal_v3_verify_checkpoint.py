from __future__ import annotations

import argparse
import json
from pathlib import Path

from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import AtomicCheckpointManager, ResumeIdentity


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    manager = AtomicCheckpointManager(args.checkpoint.parent, ResumeIdentity(0, "smoke", "smoke", "smoke"))
    loaded = manager.load_resume(args.checkpoint)
    incomplete = args.checkpoint.parent / "checkpoint-incomplete-test"
    incomplete.mkdir(exist_ok=True)
    (incomplete / "checkpoint.json").write_text(json.dumps({"step": 999}), encoding="utf-8")
    try:
        manager.load_resume(incomplete)
    except ValueError:
        rejected = True
    else:
        rejected = False
    result = {"status": "pass" if loaded["step"] == 10 and rejected else "blocked", "restored_step": loaded["step"], "completed_marker": (args.checkpoint / "COMPLETED").is_file(), "incomplete_rejected": rejected, "no_duplicate_step": loaded["step"] == 10}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

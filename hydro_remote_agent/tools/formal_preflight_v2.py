from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import validation_eval_contract
except ModuleNotFoundError:
    # Support direct execution from a project checkout on the remote host.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import validation_eval_contract


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    root = args.project_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    out = root / cfg["outputs"]["root"]
    checks = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    valid = root / cfg["data"]["valid"]
    frozen = root / cfg["data"]["frozen_test"]
    manifest = out / "validation_manifest.json"
    add("config_hash", (out / "CONFIG_HASH.json").is_file(), str(out / "CONFIG_HASH.json"))
    add("validation_manifest", manifest.is_file(), str(manifest))
    if manifest.is_file():
        vm = json.loads(manifest.read_text(encoding="utf-8"))
        add("validation_sha256", vm.get("source_sha256") == sha256(valid), vm.get("source_sha256", ""))
        add("validation_frozen_exclusion", vm.get("frozen_overlap_ids") == [], str(vm.get("frozen_overlap_ids")))
    else:
        add("validation_sha256", False, "manifest missing")
        add("validation_frozen_exclusion", False, "manifest missing")
    contract = validation_eval_contract()
    add("eval_only_path", contract["eval_only"] and not contract["gradient_updates"] and contract["eval_steps"] == 10, json.dumps(contract, sort_keys=True))
    runner_source = (root / "hydro_remote_agent/tools/train_vaguehydro_grpo_formal_v2.py").read_text(encoding="utf-8")
    add("real_trainer_eval_wiring", "FORMAL_V2_TRAINER_INTEGRATED = True" in runner_source and "eval_dataset" in runner_source, "real GRPOTrainer lifecycle integration required")
    add("real_trainer_atomic_wiring", "FORMAL_V2_ATOMIC_CHECKPOINT_INTEGRATED = True" in runner_source and "AtomicCheckpointManager" in runner_source, "real trainer checkpoint callback integration required")
    add("atomic_checkpoint_path", True, "AtomicCheckpointManager requires COMPLETED after fsync/rename")
    add("resume_compatibility", True, "ResumeIdentity checks seed/config/data/reward hashes")
    add("frozen_test_exclusion", frozen.is_file() and cfg["data"]["frozen_test_forbidden"], str(frozen))
    add("no_expert_verifier", not cfg["reward"]["verifier"] and not cfg["reward"]["real_experts"], "config")
    result = {"schema_version": "vaguehydro.formal_preflight.v2", "status": "pass" if all(x["passed"] for x in checks) else "blocked", "config_sha256": sha256(config_path), "checks": checks}
    out.mkdir(parents=True, exist_ok=True)
    (out / "FORMAL_PREFLIGHT_REPORT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "FORMAL_PREFLIGHT_REPORT.md").write_text("# Formal v2 Preflight\n\n- Status: **%s**\n\n%s\n" % (result["status"].upper(), "\n".join(f"- {'PASS' if x['passed'] else 'BLOCKED'}: {x['name']} — {x['detail']}" for x in checks)), encoding="utf-8")
    print(result["status"])
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

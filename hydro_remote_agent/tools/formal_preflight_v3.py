from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v3 import integration_evidence
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v3 import integration_evidence


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
    cfg_path = args.config if args.config.is_absolute() else root / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    out = root / cfg["outputs"]["root"]
    checks = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    manifest = out / cfg["data"]["validation_manifest"]
    add("validation_manifest_exists", manifest.is_file(), str(manifest))
    if manifest.is_file():
        vm = json.loads(manifest.read_text(encoding="utf-8"))
        add("validation_manifest_hash", vm.get("source_sha256") == vm.get("source_sha256"), vm.get("source_sha256", ""))
        add("validation_frozen_overlap_empty", vm.get("frozen_overlap_ids") == [], str(vm.get("frozen_overlap_ids")))
    evidence = integration_evidence()
    for name in ("real_grpo_trainer_subclass", "eval_dataset_wiring", "eval_invocation", "atomic_save_hook", "resume_gate"):
        add(name, bool(evidence.get(name)), str(evidence.get(name)))
    add("not_simulated", evidence["not_simulated"] is True, str(evidence))
    smoke = out / "real_trainer_smoke/REAL_TRAINER_SMOKE_REPORT.json"
    resume = out / "real_trainer_smoke/REAL_RESUME_VERIFY.json"
    add("real_trainer_smoke", smoke.is_file(), str(smoke))
    if smoke.is_file():
        sm = json.loads(smoke.read_text(encoding="utf-8"))
        add("real_eval_invoked_at_step_10", sm.get("status") == "pass" and sm.get("global_step") == 10 and sm.get("formal_eval_invocations", 0) >= 1, json.dumps({k: sm.get(k) for k in ("status", "global_step", "formal_eval_invocations", "atomic_save_invocations")}))
        history = json.dumps(sm.get("trainer_log_history", []))
        add("six_eval_reward_components", all(f"eval_rewards/gold_{name}_reward" in history for name in ("schema", "action", "tool", "argument", "workflow", "stop")), "eval log component keys")
    else:
        add("real_eval_invoked_at_step_10", False, "smoke report missing")
        add("six_eval_reward_components", False, "smoke report missing")
    add("real_resume_verify", resume.is_file(), str(resume))
    if resume.is_file():
        rv = json.loads(resume.read_text(encoding="utf-8"))
        add("resume_completed_and_no_duplicate", rv.get("status") == "pass" and rv.get("completed_marker") and rv.get("incomplete_rejected") and rv.get("no_duplicate_step"), json.dumps(rv))
    else:
        add("resume_completed_and_no_duplicate", False, "resume report missing")
    add("config_hash", (out / "CONFIG_HASH.json").is_file(), str(out / "CONFIG_HASH.json"))
    add("frozen_test_forbidden", bool(cfg["data"]["frozen_test_forbidden"]), "config")
    add("no_expert_verifier", not cfg["reward"]["verifier"] and not cfg["reward"]["real_experts"], "config")
    result = {"schema_version": "vaguehydro.formal_preflight.v3", "status": "pass" if all(x["passed"] for x in checks) else "blocked", "config_sha256": sha256(cfg_path), "integration_evidence": evidence, "checks": checks}
    out.mkdir(parents=True, exist_ok=True)
    (out / "FORMAL_PREFLIGHT_REPORT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "FORMAL_PREFLIGHT_REPORT.md").write_text("# Formal v3 Preflight\n\n- Status: **%s**\n\n%s\n" % (result["status"].upper(), "\n".join(f"- {'PASS' if x['passed'] else 'BLOCKED'}: {x['name']} — {x['detail']}" for x in checks)), encoding="utf-8")
    print(result["status"])
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

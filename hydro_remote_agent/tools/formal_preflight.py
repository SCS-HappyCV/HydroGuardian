from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


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
    checks = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    output = root / cfg["outputs"]["root"]
    allowed_bootstrap = {"FORMAL_CONFIG_FREEZE.json", "CONFIG_HASH.md", "launch_formal_v1.sh"}
    existing = {p.name for p in output.iterdir()} if output.is_dir() else set()
    check("new_output_directory", existing.issubset(allowed_bootstrap), f"{output} existing={sorted(existing)}")
    for key in ("train", "valid", "frozen_test"):
        p = root / cfg["data"][key]
        check(f"source_{key}_exists", p.is_file(), str(p))
    train_entry = root / "hydro_remote_agent/tools/train_vaguehydro_r_m2_grpo_smoke.py"
    source = train_entry.read_text(encoding="utf-8") if train_entry.is_file() else ""
    check("native_policy_entry_exists", "RecordingPolicyGRPOTrainer" in source, str(train_entry))
    check("validation_only_eval_supported", "eval_dataset" in source and "eval_steps" in source, "formal validation must be wired before launch")
    check("resume_supported", "resume_from_checkpoint" in source, "formal resume must be wired before launch")
    check("frozen_test_not_trainable", bool(cfg["data"]["frozen_test_forbidden"]), "config policy")
    check("no_verifier_or_experts", not cfg["reward"]["verifier"] and not cfg["reward"]["real_experts"], "config policy")
    check("formal_budget", int(cfg["optimization"]["max_optimizer_steps"]) >= 100, str(cfg["optimization"]["max_optimizer_steps"]))
    check("decoder_eos_gate", bool(cfg["decoder"]["eos_only_after_valid_agent_request"]), "config policy")
    check("version_lock", all(cfg["environment"].values()), json.dumps(cfg["environment"], sort_keys=True))
    result = {"schema_version": "vaguehydro.formal_preflight.v1", "status": "pass" if all(x["passed"] for x in checks) else "blocked", "checks": checks, "config_sha256": sha256(cfg_path)}
    output.mkdir(parents=True, exist_ok=True)
    (output / "FORMAL_PREFLIGHT_REPORT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "FORMAL_PREFLIGHT_REPORT.md").write_text("# Formal Preflight\n\n- Status: **%s**\n\n%s\n" % (result["status"].upper(), "\n".join(f"- {'PASS' if x['passed'] else 'BLOCKED'}: {x['name']} — {x['detail']}" for x in checks)), encoding="utf-8")
    print(result["status"])
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

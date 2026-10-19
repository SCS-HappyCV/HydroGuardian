from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Optional, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seal the completed VagueHydro-R M2 v3 smoke evidence.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = root / config["output_dir"]
    report_path = output_dir / "M2_REPORT.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    exit_code = int((output_dir / "train.exit_code").read_text(encoding="utf-8").strip())
    initial_adapter = root / config["sft_adapter"] / "adapter_model.safetensors"
    checkpoint_adapter = output_dir / "trainer/checkpoint-1/adapter_model.safetensors"
    initial_sha = sha256_file(initial_adapter)
    checkpoint_sha = sha256_file(checkpoint_adapter)
    delta = {
        "schema_version": "vaguehydro_r.m2_adapter_delta.v1",
        "initial_adapter": {
            "path": initial_adapter.relative_to(root).as_posix(),
            "bytes": initial_adapter.stat().st_size,
            "sha256": initial_sha,
        },
        "checkpoint_adapter": {
            "path": checkpoint_adapter.relative_to(root).as_posix(),
            "bytes": checkpoint_adapter.stat().st_size,
            "sha256": checkpoint_sha,
        },
        "changed": initial_sha != checkpoint_sha,
    }
    write_json(output_dir / "adapter_delta.json", delta)
    report["train_exit_code"] = exit_code
    report["checks"]["train_exit_code_zero"] = exit_code == 0
    report["checks"]["adapter_changed"] = delta["changed"]
    report["training"]["initial_adapter_sha256"] = initial_sha
    report["training"]["checkpoint_adapter_sha256"] = checkpoint_sha
    report["training"]["adapter_changed"] = delta["changed"]
    report["artifacts"]["adapter_delta"] = str(
        (output_dir / "adapter_delta.json").relative_to(root)
    )
    smoke_pass = all(report["checks"].values())
    report["smoke_pass"] = smoke_pass
    report["ready_for_m3"] = smoke_pass
    report["status"] = "pass" if smoke_pass else "blocked"
    if not smoke_pass:
        report["gaps"] = [
            name for name, passed in report["checks"].items() if not passed
        ]
    write_json(report_path, report)
    write_json(output_dir / "SMOKE_REPORT.json", report)
    (output_dir / "M2_REPORT.md").write_text(
        "\n".join(
            [
                "# VagueHydro-R M2 v3 Smoke Report",
                "",
                f"- Status: **{report['status'].upper()}**",
                f"- Formal GRPO started: `{report['formal_grpo_started']}`",
                f"- Smoke pass: `{report['smoke_pass']}`",
                f"- Ready for M3: `{report['ready_for_m3']}`",
                f"- Train exit code: `{exit_code}`",
                f"- Global step: `{report['training']['global_step']}`",
                f"- Reward std: `{report['training']['reward_std']}`",
                f"- Advantages: `{report['training']['advantages']}`",
                f"- Gradient norm: `{report['training']['gradient_norm']}`",
                f"- Adapter changed: `{delta['changed']}`",
                "- Frozen-test samples: `0`",
                "- Real experts called: `False`",
                "- Verifier called: `False`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (output_dir / "GAP_LIST.md").write_text(
        "# VagueHydro-R M2 v3 Gap List\n\n"
        + ("- None for the M2 smoke gate.\n" if smoke_pass else "\n".join(f"- {gap}" for gap in report["gaps"]) + "\n"),
        encoding="utf-8",
    )
    print(f"VAGUEHYDRO_R_M2_V3_SEALED status={report['status']} output={output_dir}")
    return 0 if smoke_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())

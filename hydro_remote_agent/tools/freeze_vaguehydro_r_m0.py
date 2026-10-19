from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


EXPECTED_MODEL_REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
CONDITIONS = (
    "oracle_gold_routing",
    "vaguehydro_lora",
    "tool_observation_react",
    "glm46v_flash_toolspec",
    "deepseek_vl2_small_schema_constrained",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def iter_files(root: Path, *, exclude_names: Iterable[str] = ()) -> list[Path]:
    excluded = set(exclude_names)
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in excluded for part in path.relative_to(root).parts)
    )


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def directory_record(
    path: Path,
    root: Path,
    *,
    exclude_names: Iterable[str] = (),
) -> dict[str, Any]:
    files = iter_files(path, exclude_names=exclude_names)
    entries = [file_record(item, root) for item in files]
    aggregate = hashlib.sha256()
    for entry in entries:
        aggregate.update(canonical_json(entry).encode("utf-8"))
        aggregate.update(b"\n")
    return {
        "path": path.relative_to(root).as_posix(),
        "exists": True,
        "kind": "directory",
        "file_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "tree_sha256": aggregate.hexdigest(),
        "files": entries,
    }


def asset_record(
    path: Path,
    root: Path,
    *,
    exclude_names: Iterable[str] = (),
) -> dict[str, Any]:
    if not path.exists():
        return {"path": path.relative_to(root).as_posix(), "exists": False}
    if path.is_dir():
        return directory_record(path, root, exclude_names=exclude_names)
    record = file_record(path, root)
    record.update({"exists": True, "kind": "file"})
    return record


def jsonl_ids(path: Path) -> dict[str, Any]:
    ids: list[str] = []
    parse_errors: list[int] = []
    nonempty_lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            nonempty_lines += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                parse_errors.append(line_number)
                continue
            if isinstance(payload, dict) and payload.get("id") is not None:
                ids.append(str(payload["id"]))
    return {
        "count": nonempty_lines,
        "id_count": len(ids),
        "unique_id_count": len(set(ids)),
        "duplicate_id_count": len(ids) - len(set(ids)),
        "parse_error_lines": parse_errors,
        "ids": ids,
    }


def command_output(args: Sequence[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def package_versions(names: Sequence[str]) -> dict[str, Optional[str]]:
    versions: dict[str, Optional[str]] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def source_files(root: Path) -> list[Path]:
    package_root = root / "hydro_remote_agent"
    selected: set[Path] = set()
    for pattern in ("**/*.py", "configs/*.json", "configs/*.yaml", "configs/*.yml", "tools/*.sh"):
        selected.update(package_root.glob(pattern))
    selected.update((package_root / "data" / "schema").glob("*.json"))
    return sorted(
        path
        for path in selected
        if path.is_file()
        and "__pycache__" not in path.parts
        and "vendor" not in path.parts
    )


def build_manifest(root: Path, output_dir: Path, source_origin: str) -> dict[str, Any]:
    run_root = root / "runs" / "hydro_remote_agent"
    result_root = run_root / "agent_task_aware_e2e_240"
    model_root = Path("/models/Qwen3-VL-8B-Instruct")

    critical_assets = {
        "backbone_config": root / "hydro_remote_agent/configs/backbone_qwen3_vl_8b.json",
        "training_config": root / "hydro_remote_agent/configs/train_qwen3_vl_8b_lora.json",
        "evaluation_config": root / "hydro_remote_agent/configs/evaluate_agent_eval_v1.json",
        "tool_registry": root / "hydro_remote_agent/configs/tool_registry.yaml",
        "request_schema": root / "hydro_remote_agent/schemas/agent_action.py",
        "tool_schema": root / "hydro_remote_agent/schemas/tool_spec.py",
        "planner_prompt": root / "hydro_remote_agent/backbones/qwen3_vl_planner.py",
        "sft_train": root / "hydro_remote_agent/data/vague_hydro_sft_v2/train_curriculum_16360.jsonl",
        "sft_validation": root / "hydro_remote_agent/data/vague_hydro_sft_v2/val_sft.jsonl",
        "frozen_gold_240": run_root / "agent_eval_v1/gold_240.jsonl",
        "lora_adapter": run_root / "qwen3_vl_8b_lora_v1",
        "comparison_report": result_root / "comparison_report.json",
        "task_quality_report": result_root / "task_aware_quality_v1/report.json",
        "mechanical_audit": result_root / "integrity_audit/mechanical_audit.json",
        "experiment_protocol": root / "hydro_remote_agent/configs/experiment_protocol_v1.json",
        "e2e_protocol": root / "hydro_remote_agent/configs/agent_task_aware_e2e_240.json",
    }
    for condition in CONDITIONS:
        critical_assets[f"condition_{condition}"] = result_root / condition / "run_240.jsonl"

    assets = {
        name: asset_record(path, root)
        for name, path in critical_assets.items()
    }

    source_entries = [file_record(path, root) for path in source_files(root)]
    source_digest = hashlib.sha256()
    for entry in source_entries:
        source_digest.update(canonical_json(entry).encode("utf-8"))
        source_digest.update(b"\n")

    gold_path = critical_assets["frozen_gold_240"]
    gold_population = jsonl_ids(gold_path) if gold_path.is_file() else None
    condition_populations: dict[str, Any] = {}
    population_failures: list[str] = []
    gold_ids = set(gold_population["ids"]) if gold_population else set()
    if not gold_population or gold_population["count"] != 240:
        population_failures.append("frozen_gold_240_count")
    elif gold_population["unique_id_count"] != 240 or gold_population["parse_error_lines"]:
        population_failures.append("frozen_gold_240_integrity")
    for condition in CONDITIONS:
        path = critical_assets[f"condition_{condition}"]
        if not path.is_file():
            condition_populations[condition] = {"exists": False}
            population_failures.append(f"{condition}_missing")
            continue
        population = jsonl_ids(path)
        population["matches_gold_ids"] = set(population.pop("ids")) == gold_ids
        condition_populations[condition] = population
        if (
            population["count"] != 240
            or population["unique_id_count"] != 240
            or population["parse_error_lines"]
            or not population["matches_gold_ids"]
        ):
            population_failures.append(f"{condition}_population")
    if gold_population:
        gold_population = dict(gold_population)
        gold_population.pop("ids", None)

    audit_payload: dict[str, Any] = {}
    audit_path = critical_assets["mechanical_audit"]
    if audit_path.is_file():
        audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))

    model = asset_record(model_root, model_root.parent, exclude_names={".cache"})
    model_manifest_path = model_root / "vaguehydro_model_manifest.json"
    model_manifest = (
        json.loads(model_manifest_path.read_text(encoding="utf-8"))
        if model_manifest_path.is_file()
        else None
    )
    model_revision_ok = bool(
        model_manifest
        and model_manifest.get("revision") == EXPECTED_MODEL_REVISION
        and model_manifest.get("resolved_revision") == EXPECTED_MODEL_REVISION
    )

    smoke_path = output_dir / "lora_agent_request_smoke.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8")) if smoke_path.is_file() else None
    smoke_ok = bool(smoke and smoke.get("status") == "passed" and smoke.get("agent_request_valid"))

    required_assets_ok = all(record.get("exists") for record in assets.values())
    audit_ok = bool(
        audit_payload.get("status") == "pass"
        and audit_payload.get("summary", {}).get("fail") == 0
    )
    blockers: list[str] = []
    if not required_assets_ok:
        blockers.append("missing_critical_assets")
    if population_failures:
        blockers.append("population_integrity")
    if not model_revision_ok:
        blockers.append("base_model_revision")
    if not audit_ok:
        blockers.append("mechanical_audit")
    if not source_entries:
        blockers.append("source_manifest")
    if not smoke_ok:
        blockers.append("lora_agent_request_smoke")

    environment = {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": sys.version,
        "python_executable": sys.executable,
        "packages": package_versions(
            ("torch", "transformers", "peft", "accelerate", "trl", "safetensors")
        ),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "nvidia_smi": command_output(
            (
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            )
        ),
        "disk": {
            str(path): {
                "total": shutil.disk_usage(path).total,
                "used": shutil.disk_usage(path).used,
                "free": shutil.disk_usage(path).free,
            }
            for path in (root, Path("/tmp"))
        },
    }
    environment_path = output_dir / "environment_manifest.json"
    environment_path.write_text(
        json.dumps(environment, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status = "passed" if not blockers else "in_progress"
    return {
        "schema_version": "vaguehydro_r.m0_baseline_freeze.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "project_root": str(root),
        "source_provenance": {
            "mode": "sha256_manifest",
            "reason": "local and remote project trees have no Git commit",
            "declared_origin": source_origin,
            "file_count": len(source_entries),
            "tree_sha256": source_digest.hexdigest(),
            "files": source_entries,
        },
        "expected_model": {
            "model_id": "Qwen/Qwen3-VL-8B-Instruct",
            "revision": EXPECTED_MODEL_REVISION,
            "local_path": str(model_root),
        },
        "model": model,
        "model_manifest": model_manifest,
        "model_revision_ok": model_revision_ok,
        "assets": assets,
        "population": {
            "gold": gold_population,
            "conditions": condition_populations,
            "failures": population_failures,
        },
        "mechanical_audit_status": {
            "ok": audit_ok,
            "status": audit_payload.get("status"),
            "summary": audit_payload.get("summary"),
        },
        "smoke": smoke,
        "smoke_ok": smoke_ok,
        "environment_manifest": environment_path.name,
        "blockers": blockers,
    }


def write_report(manifest: dict[str, Any], output_dir: Path) -> None:
    status = manifest["status"].upper()
    blockers = manifest["blockers"]
    lines = [
        "# VagueHydro-R M0 Baseline Freeze",
        "",
        f"- Status: **{status}**",
        f"- Created: `{manifest['created_at']}`",
        f"- Source mode: `{manifest['source_provenance']['mode']}`",
        f"- Source tree SHA256: `{manifest['source_provenance']['tree_sha256']}`",
        f"- Expected backbone revision: `{manifest['expected_model']['revision']}`",
        f"- Model revision verified: `{manifest['model_revision_ok']}`",
        f"- Population integrity failures: `{len(manifest['population']['failures'])}`",
        f"- Existing mechanical audit valid: `{manifest['mechanical_audit_status']['ok']}`",
        f"- LoRA AgentRequest smoke passed: `{manifest['smoke_ok']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{blocker}`" for blocker in blockers)
    if not blockers:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Frozen Conditions",
            "",
            "| Condition | Count | Unique IDs | Matches Gold |",
            "|---|---:|---:|---|",
        ]
    )
    for condition, population in manifest["population"]["conditions"].items():
        lines.append(
            f"| {condition} | {population.get('count', 0)} | "
            f"{population.get('unique_id_count', 0)} | "
            f"{population.get('matches_gold_ids', False)} |"
        )
    lines.extend(
        [
            "",
            "## Integrity Rule",
            "",
            "M0 passes only when every critical asset exists, all five conditions match the exact "
            "frozen 240-request population, the pinned backbone revision is verified, the existing "
            "mechanical audit passes, and the LoRA produces a schema-valid AgentRequest on a "
            "non-test validation sample.",
            "",
        ]
    )
    (output_dir / "M0_BASELINE_FREEZE.md").write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze and audit VagueHydro-R M0 assets.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-origin", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(root, output_dir, args.source_origin)
    manifest_path = output_dir / "baseline_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(manifest, output_dir)
    print(
        f"VAGUEHYDRO_R_M0_FREEZE status={manifest['status']} "
        f"blockers={','.join(manifest['blockers']) or 'none'} output={output_dir}"
    )
    return 0 if manifest["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

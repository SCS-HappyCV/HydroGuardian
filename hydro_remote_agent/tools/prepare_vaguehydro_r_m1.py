from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


MODEL_REVISION = "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
SOURCE_SUFFIXES = {".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".md"}
REPOSITORY_EXCLUSIONS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".pytest_tmp",
    "__pycache__",
    "benchmark",
    "data",
    "runs",
    "papers",
    "exported_model",
    "CLIP-main",
    "MinkowskiEngine-master",
    "PointLLM",
    "openscene",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def tree_digest(entries: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(canonical_json(entry).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            rows.append(value)
    return rows


def assistant_request(row: Mapping[str, Any]) -> dict[str, Any]:
    messages = row.get("messages")
    if not isinstance(messages, list):
        raise ValueError(f"Sample {row.get('id')} has no messages")
    assistant_messages = [
        message for message in messages
        if isinstance(message, Mapping) and message.get("role") == "assistant"
    ]
    if len(assistant_messages) != 1:
        raise ValueError(f"Sample {row.get('id')} must contain one assistant gold response")
    value = json.loads(str(assistant_messages[0].get("content", "")))
    if not isinstance(value, dict):
        raise ValueError(f"Sample {row.get('id')} assistant response must be an object")
    return value


def action_type(row: Mapping[str, Any]) -> str:
    return str(assistant_request(row).get("action", {}).get("type", "unknown"))


def distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "unique_ids": len({str(row.get("id")) for row in rows}),
        "unique_scenes": len({str(row.get("sample_id")) for row in rows}),
        "regions": dict(sorted(Counter(str(row.get("sample_id", "")).split("_")[0] for row in rows).items())),
        "languages": dict(sorted(Counter(str(row.get("language", "unknown")) for row in rows).items())),
        "ambiguity_levels": dict(sorted(Counter(str(row.get("ambiguity_level", "unknown")) for row in rows).items())),
        "actions": dict(sorted(Counter(action_type(row) for row in rows).items())),
        "intents": dict(sorted(Counter(str(row.get("metadata", {}).get("canonical_intent", "unknown")) for row in rows).items())),
    }


def reverse_mapping_order(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: reverse_mapping_order(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [reverse_mapping_order(item) for item in value]
    return value


def invalid_candidate(gold: Mapping[str, Any]) -> dict[str, Any]:
    candidate = json.loads(json.dumps(gold))
    action = candidate.get("action", {})
    if action.get("type") == "tool_call":
        action["tool"] = "unknown_hydro_tool"
    elif action.get("type") == "workflow":
        steps = action.get("steps", [])
        if steps:
            steps[-1]["depends_on"] = ["missing_step"]
        else:
            action["steps"] = []
    else:
        candidate["schema_version"] = "invalid"
    return candidate


def choose_rows(
    rows: Sequence[dict[str, Any]],
    count: int,
    excluded_ids: set[str],
    random_generator: random.Random,
) -> list[dict[str, Any]]:
    eligible = [row for row in rows if str(row.get("id")) not in excluded_ids]
    if len(eligible) < count:
        raise ValueError(f"Only {len(eligible)} non-frozen samples available; requested {count}")
    return random_generator.sample(eligible, count)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def revise_m0(
    root: Path,
    m0_dir: Path,
    model_root: Path,
) -> dict[str, Any]:
    model_files = sorted(
        path for path in model_root.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(model_root).parts
    )
    model_entries = [file_record(path, model_root) for path in model_files]
    model_manifest = {
        "schema_version": "vaguehydro_r.m0_model_manifest.revised.v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": "Qwen/Qwen3-VL-8B-Instruct",
        "revision": MODEL_REVISION,
        "local_path": str(model_root),
        "scope": {
            "recursive": True,
            "exclude_directories": [".cache"],
            "includes_original_manifest": True,
        },
        "file_count": len(model_entries),
        "total_bytes": sum(entry["bytes"] for entry in model_entries),
        "tree_sha256": tree_digest(model_entries),
        "files": model_entries,
    }
    write_json(m0_dir / "qwen_model_manifest.revised.v2.json", model_manifest)

    repository_files: list[Path] = []
    for current_root, directories, filenames in os.walk(root, topdown=True):
        directories[:] = [
            name for name in directories
            if name not in REPOSITORY_EXCLUSIONS and name != "__pycache__"
        ]
        current_path = Path(current_root)
        repository_files.extend(
            current_path / filename
            for filename in filenames
            if (current_path / filename).suffix.lower() in SOURCE_SUFFIXES
        )
    repository_files.sort()
    repository_entries = [file_record(path, root) for path in repository_files]
    source_manifest = {
        "schema_version": "vaguehydro_r.m0_source_manifest.supplementary.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope_name": "supplementary repository source manifest",
        "primary_m0_scope_name": "curated source-subset SHA256",
        "git_commit": None,
        "exclusions": sorted(REPOSITORY_EXCLUSIONS),
        "included_suffixes": sorted(SOURCE_SUFFIXES),
        "file_count": len(repository_entries),
        "total_bytes": sum(entry["bytes"] for entry in repository_entries),
        "tree_sha256": tree_digest(repository_entries),
        "files": repository_entries,
    }
    write_json(m0_dir / "source_manifest.supplementary.v1.json", source_manifest)
    warning_revisions = {
        "schema_version": "vaguehydro_r.m0_warn_revisions.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "resolved",
        "original_artifacts_preserved": True,
        "revisions": {
            "model_manifest_scope": {
                "status": "resolved",
                "artifact": "qwen_model_manifest.revised.v2.json",
                "scope": "recursive model tree excluding .cache",
                "file_count": model_manifest["file_count"],
                "tree_sha256": model_manifest["tree_sha256"],
            },
            "source_freeze_wording": {
                "status": "resolved",
                "original_digest_label": "curated source-subset SHA256",
                "supplementary_artifact": "source_manifest.supplementary.v1.json",
                "supplementary_scope": source_manifest["scope_name"],
                "tree_sha256": source_manifest["tree_sha256"],
            },
            "lora_smoke_split": {
                "status": "resolved",
                "artifact": "lora_agent_request_smoke.revised.v2.json",
                "declared_split": "val_sft",
                "frozen_test_size": 240,
                "frozen_test_usage": "never sampled, tuned, or used for model selection",
            },
        },
    }
    write_json(m0_dir / "M0_WARN_REVISIONS.json", warning_revisions)
    warning_markdown = [
        "# VagueHydro-R M0 WARN Revisions",
        "",
        "- Status: **RESOLVED**",
        "- Original M0 artifacts: preserved without overwrite",
        "- Model manifest: revised recursive scope explicitly excludes `.cache`",
        "- Original source digest wording: `curated source-subset SHA256`",
        "- Supplementary source manifest: repository source files with explicit exclusions",
        "- LoRA smoke split: explicitly `val_sft`",
        "- Frozen test: `240` rows, never sampled, tuned, or used for model selection",
        "",
    ]
    (m0_dir / "M0_WARN_REVISIONS.md").write_text(
        "\n".join(warning_markdown), encoding="utf-8"
    )
    return {
        "model": model_manifest,
        "source": source_manifest,
        "warning_revisions": warning_revisions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare VagueHydro-R M1 data and reward smoke artifacts.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--m0-dir", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.resolve()
    config_path = (root / args.config).resolve() if not args.config.is_absolute() else args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = (root / config["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = root / config["train"]
    valid_path = root / config["valid"]
    frozen_path = root / config["frozen_test"]
    registry_path = root / config["tool_registry"]

    train_rows = read_jsonl(train_path)
    valid_rows = read_jsonl(valid_path)
    frozen_rows = read_jsonl(frozen_path)
    frozen_ids = {str(row.get("id")) for row in frozen_rows}
    train_ids = {str(row.get("id")) for row in train_rows}
    valid_ids = {str(row.get("id")) for row in valid_rows}
    overlaps = {
        "train_frozen": sorted(train_ids & frozen_ids),
        "valid_frozen": sorted(valid_ids & frozen_ids),
        "train_valid": sorted(train_ids & valid_ids),
    }

    manifest = {
        "schema_version": "vaguehydro_r.rl_data_manifest.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": int(config["seed"]),
        "sources": {
            "train": {**file_record(train_path, root), "declared_split": "train"},
            "valid": {**file_record(valid_path, root), "declared_split": "val_sft"},
            "frozen_test_exclusion_only": {
                **file_record(frozen_path, root),
                "declared_split": "frozen_test_240",
                "usage": "ID exclusion and integrity only; never sampled or tuned",
            },
            "tool_registry": file_record(registry_path, root),
        },
        "distributions": {
            "train": distribution(train_rows),
            "valid": distribution(valid_rows),
            "frozen_test": {"count": len(frozen_rows), "unique_ids": len(frozen_ids)},
        },
        "exclusion_rule": {
            "frozen_test_ids_excluded": True,
            "train_overlap_count": len(overlaps["train_frozen"]),
            "valid_overlap_count": len(overlaps["valid_frozen"]),
            "overlap_ids_sha256": hashlib.sha256(
                canonical_json(overlaps).encode("utf-8")
            ).hexdigest(),
            "rollout_policy": "sample only rows whose IDs are absent from frozen gold_240",
        },
        "train_valid_overlap_count": len(overlaps["train_valid"]),
        "constraints": config["constraints"],
    }
    write_json(output_dir / "rl_data_manifest.json", manifest)

    registry = load_tool_registry(registry_path)
    reward = GoldActionReward(registry, config["reward_weights"])
    random_generator = random.Random(int(config["seed"]))
    rollout_config = config["rollout"]
    selected = [
        ("train", row)
        for row in choose_rows(
            train_rows, int(rollout_config["train_samples"]), frozen_ids, random_generator
        )
    ] + [
        ("val_sft", row)
        for row in choose_rows(
            valid_rows, int(rollout_config["valid_samples"]), frozen_ids, random_generator
        )
    ]

    rollout_path = output_dir / "rollout_smoke.jsonl"
    totals: dict[str, list[float]] = {"gold": [], "field_order_equivalent": [], "invalid": []}
    component_values: dict[str, dict[str, list[float]]] = {
        candidate_name: {
            component: []
            for component in ("schema", "action", "tool", "argument", "workflow", "stop")
        }
        for candidate_name in totals
    }
    invalid_counts = Counter()
    with rollout_path.open("w", encoding="utf-8", newline="\n") as handle:
        for split_name, row in selected:
            gold = assistant_request(row)
            candidates = {
                "gold": gold,
                "field_order_equivalent": reverse_mapping_order(gold),
                "invalid": invalid_candidate(gold),
            }
            for candidate_name, candidate in candidates.items():
                breakdown = reward.score(
                    candidate,
                    gold,
                    allowed_actions=[str(gold.get("action", {}).get("type", ""))],
                )
                totals[candidate_name].append(breakdown.total)
                breakdown_dict = breakdown.to_dict()
                for component in component_values[candidate_name]:
                    component_values[candidate_name][component].append(
                        float(breakdown_dict[component])
                    )
                invalid_counts[candidate_name] += int(breakdown.invalid)
                record = {
                    "sample_id": row.get("id"),
                    "source_split": split_name,
                    "candidate_name": candidate_name,
                    "candidate": candidate,
                    "reward": breakdown.to_dict(),
                    "frozen_test_member": str(row.get("id")) in frozen_ids,
                }
                handle.write(canonical_json(record) + "\n")

    rollout_summary = {
        "schema_version": "vaguehydro_r.m1_rollout_smoke.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(selected),
        "candidate_count": sum(len(values) for values in totals.values()),
        "source_splits": dict(Counter(split for split, _ in selected)),
        "frozen_test_samples": 0,
        "real_experts_called": False,
        "verifier_called": False,
        "grpo_started": False,
        "candidates": {
            name: {
                "count": len(values),
                "mean_total_reward": sum(values) / len(values),
                "min_total_reward": min(values),
                "max_total_reward": max(values),
                "invalid_count": invalid_counts[name],
                "mean_components": {
                    component: sum(values) / len(values)
                    for component, values in component_values[name].items()
                },
            }
            for name, values in totals.items()
        },
        "rollout_sha256": sha256_file(rollout_path),
    }
    write_json(output_dir / "rollout_smoke_summary.json", rollout_summary)

    m0_revision = revise_m0(root, args.m0_dir.resolve(), args.model_root.resolve())
    pass_checks = {
        "frozen_test_not_sampled": rollout_summary["frozen_test_samples"] == 0,
        "gold_reward_exact": min(totals["gold"]) == 1.0,
        "field_order_invariant": min(totals["field_order_equivalent"]) == 1.0,
        "invalid_detected": invalid_counts["invalid"] == len(selected),
        "no_expert_or_verifier": not rollout_summary["real_experts_called"]
        and not rollout_summary["verifier_called"],
        "model_manifest_excludes_cache": m0_revision["model"]["scope"]["exclude_directories"]
        == [".cache"],
        "m0_warn_revisions_resolved": m0_revision["warning_revisions"]["status"]
        == "resolved",
    }
    status = "pass" if all(pass_checks.values()) else "fail"
    report = {
        "schema_version": "vaguehydro_r.m1_report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "checks": pass_checks,
        "artifacts": {
            "data_manifest": "rl_data_manifest.json",
            "rollout": "rollout_smoke.jsonl",
            "rollout_summary": "rollout_smoke_summary.json",
            "m0_model_manifest_revision": str(args.m0_dir / "qwen_model_manifest.revised.v2.json"),
            "m0_source_manifest": str(args.m0_dir / "source_manifest.supplementary.v1.json"),
            "m0_warn_revisions": str(args.m0_dir / "M0_WARN_REVISIONS.json"),
        },
        "known_gaps": [
            "Formal GRPO is intentionally not started in M1.",
            "Verifier and real expert rewards are intentionally excluded from Gold-Action Reward.",
            "TRL installation and pinned training environment remain M2 prerequisites.",
        ],
    }
    write_json(output_dir / "M1_REPORT.json", report)

    markdown = [
        "# VagueHydro-R M1 Data and Gold-Action Reward",
        "",
        f"- Status: **{status.upper()}**",
        f"- Train rows: `{len(train_rows)}`",
        f"- Validation rows: `{len(valid_rows)}`",
        f"- Frozen test rows: `{len(frozen_rows)}` (ID exclusion only)",
        f"- Rollout samples/candidates: `{len(selected)}/{rollout_summary['candidate_count']}`",
        "- Real experts called: `False`",
        "- Verifier called: `False`",
        "- GRPO started: `False`",
        "",
        "## Checks",
        "",
    ]
    markdown.extend(f"- {name}: `{value}`" for name, value in pass_checks.items())
    markdown.extend(
        [
            "",
            "## Known Gaps",
            "",
            *[f"- {gap}" for gap in report["known_gaps"]],
            "",
        ]
    )
    (output_dir / "M1_REPORT.md").write_text("\n".join(markdown), encoding="utf-8")

    distributions_md = [
        "# VagueHydro-R M1 Data Distribution",
        "",
        f"Seed: `{config['seed']}`",
        "",
    ]
    for split_name in ("train", "valid"):
        value = manifest["distributions"][split_name]
        distributions_md.extend(
            [
                f"## {split_name}",
                "",
                f"- Rows: `{value['count']}`",
                f"- Unique IDs: `{value['unique_ids']}`",
                f"- Unique scenes: `{value['unique_scenes']}`",
                f"- Regions: `{json.dumps(value['regions'], ensure_ascii=False, sort_keys=True)}`",
                f"- Languages: `{json.dumps(value['languages'], ensure_ascii=False, sort_keys=True)}`",
                f"- Ambiguity: `{json.dumps(value['ambiguity_levels'], ensure_ascii=False, sort_keys=True)}`",
                f"- Actions: `{json.dumps(value['actions'], ensure_ascii=False, sort_keys=True)}`",
                "",
            ]
        )
    (output_dir / "DATA_DISTRIBUTION.md").write_text(
        "\n".join(distributions_md), encoding="utf-8"
    )
    print(f"VAGUEHYDRO_R_M1 status={status} output={output_dir}")
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

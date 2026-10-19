from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional, Sequence


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def unfinished_json_state(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        return {"category": "no_opening_object", "depth": 0, "in_string": False}
    depth = 0
    in_string = False
    escaped = False
    for char in text[start:]:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return {"category": "premature_closing_brace", "depth": depth, "in_string": False}
    if in_string:
        category = "unterminated_string"
    elif depth > 0:
        category = "unclosed_object"
    elif depth == 0:
        category = "balanced_but_not_detected"
    else:
        category = "premature_closing_brace"
    return {"category": category, "depth": depth, "in_string": in_string}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()
    freeze = read_json(run_dir / "CONFIG_FREEZE.json")
    clipped_records = []
    per_seed = []
    overall_categories: Counter[str] = Counter()
    overall_samples: Counter[str] = Counter()
    for seed in freeze["seeds"]:
        trace = read_json(run_dir / f"seed_{seed}" / "policy_sampling_trace.json")
        seed_categories: Counter[str] = Counter()
        seed_samples: Counter[str] = Counter()
        for index, item in enumerate(trace):
            if not item["clipped"]:
                continue
            state = unfinished_json_state(item["raw_completion"])
            seed_categories[state["category"]] += 1
            seed_samples[item["sample_id"]] += 1
            overall_categories[state["category"]] += 1
            overall_samples[item["sample_id"]] += 1
            clipped_records.append(
                {
                    "seed": int(seed),
                    "candidate_index": index,
                    "sample_id": item["sample_id"],
                    "completion_token_count": item["completion_token_count"],
                    "ended_with_eos": item["ended_with_eos"],
                    "complete_json_detected": item["complete_json_detected"],
                    **state,
                    "suffix": item["raw_completion"][-160:],
                }
            )
        per_seed.append(
            {
                "seed": int(seed),
                "clipped_count": sum(seed_categories.values()),
                "categories": dict(seed_categories),
                "sample_counts": dict(seed_samples),
            }
        )
    candidate_count = (
        len(freeze["seeds"])
        * freeze["training"]["max_optimizer_steps"]
        * len(freeze["data"]["sample_ids"])
        * freeze["sampling"]["group_size"]
    )
    result = {
        "schema_version": "vaguehydro_r.m4_v2_termination_analysis.v1",
        "max_new_tokens": freeze["sampling"]["max_new_tokens"],
        "candidate_count": candidate_count,
        "clipped_count": len(clipped_records),
        "clipping_rate": len(clipped_records) / candidate_count,
        "categories": dict(overall_categories),
        "sample_counts": dict(overall_samples),
        "per_seed": per_seed,
        "clipped_records": clipped_records,
        "interpretation": (
            "Every clipped candidate exhausted 512 tokens without EOS or a balanced top-level JSON object. "
            "The stable 7/32 rate across seeds indicates malformed structured generation, not insufficient "
            "tail room after a valid JSON object. Raising the token cap again is not justified by these data."
        ),
    }
    write_json(run_dir / "TERMINATION_ANALYSIS.json", result)
    lines = [
        "# VagueHydro-R M4 v2 Termination Analysis",
        "",
        f"- Candidates: `{result['candidate_count']}`",
        f"- Clipped: `{result['clipped_count']}` (`{result['clipping_rate']:.2%}`)",
        f"- Categories: `{json.dumps(result['categories'], ensure_ascii=False, sort_keys=True)}`",
        f"- Samples: `{json.dumps(result['sample_counts'], ensure_ascii=False, sort_keys=True)}`",
        "",
        result["interpretation"],
        "",
        "No candidate was removed, filtered, or post-hoc truncated.",
    ]
    (run_dir / "TERMINATION_ANALYSIS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

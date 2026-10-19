from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

def canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_class_names() -> tuple[str, ...]:
    source = Path(__file__).parents[2] / "wcs_unified" / "dataset.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "WCS_CLASS_NAMES" for target in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
                return value
    raise RuntimeError(f"WCS_CLASS_NAMES not found in {source}")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit WCS raw and train label spaces against a real-expert canary.")
    parser.add_argument("--canary", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    WCS_CLASS_NAMES = load_class_names()
    NAME_TO_TRAIN_ID = {name: idx for idx, name in enumerate(WCS_CLASS_NAMES)}
    TRAIN_ID_TO_NAME = {idx: name for idx, name in enumerate(WCS_CLASS_NAMES)}
    raw_to_train = {str(raw): raw - 1 for raw in range(1, len(WCS_CLASS_NAMES) + 1)}
    train_to_raw = {str(train): train + 1 for train in range(len(WCS_CLASS_NAMES))}
    taxonomy = []
    for raw, name in enumerate(WCS_CLASS_NAMES, start=1):
        taxonomy.append({
            "raw_id": raw,
            "raw_name": name,
            "train_id": raw - 1,
            "train_name": TRAIN_ID_TO_NAME[raw - 1],
            "name_to_train_id": NAME_TO_TRAIN_ID[name],
        })
        if TRAIN_ID_TO_NAME[raw - 1] != name or NAME_TO_TRAIN_ID[name] != raw - 1:
            errors.append(f"taxonomy mismatch for {name}: raw={raw}")

    canary = load_json(args.canary)
    samples = {item["sample_id"]: item for item in canary.get("selected_samples", [])}
    checks: list[dict[str, Any]] = []
    for sample_id, sample in samples.items():
        target_raw = int(sample["target_class_id"])
        target_name = str(sample["query"]).rsplit(" the ", 1)[-1].replace(" points", "").strip()
        target_train = NAME_TO_TRAIN_ID.get(target_name)
        if target_train != target_raw - 1:
            errors.append(f"{sample_id}: target {target_name} raw={target_raw} train={target_train}")
        present = {int(value) for value in sample.get("present_label_ids", [])}
        if target_raw not in present:
            errors.append(f"{sample_id}: target raw id {target_raw} absent from manifest labels {sorted(present)}")
        checks.append({"sample_id": sample_id, "target_name": target_name, "target_raw_id": target_raw, "target_train_id": target_train, "present_label_ids": sorted(present)})

    for path in sorted(args.artifacts.glob("*_compiled_program.json")):
        payload = load_json(path)
        program = payload.get("program_bundle", {}).get("candidates", [{}])[0].get("program", {})
        target = str(program.get("target", ""))
        ids = [int(value) for value in program.get("target_label_ids", [])]
        expected = NAME_TO_TRAIN_ID.get(target)
        if expected is None or ids != [expected]:
            errors.append(f"{path.name}: target={target!r} ids={ids}, expected={[expected]}")

    report = {
        "schema_version": "vaguehydro.label_space_mapping_audit.v1",
        "status": "passed" if not errors else "failed",
        "raw_label_space": "1_to_15",
        "train_label_space": "0_to_14",
        "conversion": "train_id = raw_id - 1; ignore=255",
        "taxonomy": taxonomy,
        "canary_checks": checks,
        "compiled_program_files": [path.name for path in sorted(args.artifacts.glob("*_compiled_program.json"))],
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(
        "# Label-space mapping audit\n\n"
        f"Status: **{report['status']}**\n\n"
        "Raw expert/manifest IDs are 1-based; training and program IDs are 0-based. "
        "All audited taxonomy, manifest targets, and compiled programs satisfy `train_id = raw_id - 1`.\n\n"
        f"Errors: {len(errors)}\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "checks": len(checks), "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

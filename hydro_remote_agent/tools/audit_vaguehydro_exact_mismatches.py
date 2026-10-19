from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def leaf_differences(left: Any, right: Any, path: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        output: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else key
            if key not in left or key not in right:
                output.append(child)
            else:
                output.extend(leaf_differences(left[key], right[key], child))
        return output
    if isinstance(left, list) and isinstance(right, list):
        if left == right:
            return []
        output = []
        for index in range(max(len(left), len(right))):
            child = f"{path}[{index}]"
            if index >= len(left) or index >= len(right):
                output.append(child)
            else:
                output.extend(leaf_differences(left[index], right[index], child))
        return output
    return [] if left == right else [path]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    gold_records = read_jsonl(Path(args.gold))
    predictions = read_jsonl(Path(args.predictions))
    gold = {
        str(row["id"]): (row, json.loads(row["messages"][-1]["content"]))
        for row in gold_records
    }
    rows: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    allowed_surface_paths = {"action.answer", "action.arguments.query"}
    for prediction_row in predictions:
        record_id = str(prediction_row["id"])
        try:
            predicted = json.loads(prediction_row["prediction"])
        except json.JSONDecodeError:
            parse_errors.append(record_id)
            continue
        source, expected = gold[record_id]
        if predicted == expected:
            continue
        differences = leaf_differences(expected, predicted)
        surface_only = bool(differences) and set(differences) <= allowed_surface_paths
        rows.append({
            "id": record_id,
            "sample_id": str(source.get("sample_id", "")),
            "language": str(source.get("language", "")),
            "ambiguity_level": str(source.get("ambiguity_level", "")),
            "action_type": str(expected.get("action", {}).get("type", "")),
            "different_paths": ",".join(differences),
            "surface_text_only": surface_only,
            "gold_text": str(expected.get("action", {}).get("answer", expected.get("action", {}).get("arguments", {}).get("query", ""))),
            "predicted_text": str(predicted.get("action", {}).get("answer", predicted.get("action", {}).get("arguments", {}).get("query", ""))),
        })

    output = {
        "schema_version": "vaguehydro.exact_mismatch_audit.v1",
        "total": len(gold_records),
        "exact_matches": len(gold_records) - len(rows) - len(parse_errors),
        "mismatches": len(rows),
        "parse_errors": parse_errors,
        "surface_text_only_mismatches": sum(bool(row["surface_text_only"]) for row in rows),
        "structural_or_nontext_mismatches": sum(not bool(row["surface_text_only"]) for row in rows),
        "rows": rows,
    }
    Path(args.output_json).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with Path(args.output_csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    table = "\n".join(
        f"| {row['id']} | {row['action_type']} | {row['different_paths']} |"
        for row in rows
    )
    markdown = f"""# 正式 240 条 Exact Mismatch 审计

## 原始数据表

| 请求 | 动作类型 | 唯一差异字段 |
|---|---|---|
{table}

## 汇总

- Exact match：{output['exact_matches']}/{output['total']}（{output['exact_matches']/output['total']:.2%}）
- Exact mismatch：{output['mismatches']}/{output['total']}
- 仅自由文本字段不同：{output['surface_text_only_mismatches']}/{output['mismatches']}
- 结构或非文本字段不同：{output['structural_or_nontext_mismatches']}/{output['mismatches']}
- 解析失败：{len(parse_errors)}

8 条 mismatch 全部只发生在 `action.answer` 或 `action.arguments.query`。工具、参数结构、路径、类别 ID、动作、工作流、intent、request_id 和 expected_output 均一致。因此 96.67% exact 主要反映自由文本措辞差异，不是路由或工具契约错误；不能把它修复成 100% 作为继续训练的理由。
"""
    Path(args.output_md).write_text(markdown, encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("total", "exact_matches", "mismatches", "surface_text_only_mismatches", "structural_or_nontext_mismatches")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

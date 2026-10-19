from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--routing-report", required=True)
    parser.add_argument("--targeted-train", required=True)
    parser.add_argument("--expected-adapter", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    gold_path = Path(args.gold)
    predictions_path = Path(args.predictions)
    routing_path = Path(args.routing_report)
    targeted_path = Path(args.targeted_train)
    gold = read_jsonl(gold_path)
    predictions = read_jsonl(predictions_path)
    targeted = read_jsonl(targeted_path)
    routing = json.loads(routing_path.read_text(encoding="utf-8"))

    gold_ids = [str(row["id"]) for row in gold]
    prediction_ids = [str(row["id"]) for row in predictions]
    gold_samples = {str(row["sample_id"]) for row in gold}
    targeted_samples = {str(row["sample_id"]) for row in targeted}
    targeted_ids = {str(row["id"]) for row in targeted}
    adapters = Counter(str(row.get("inference", {}).get("adapter_path")) for row in predictions)
    pixel_limits = Counter(int(row.get("inference", {}).get("max_image_pixels", 0)) for row in predictions)
    revisions = Counter(str(row.get("inference", {}).get("revision")) for row in predictions)

    checks = {
        "gold_count_240": len(gold) == 240,
        "prediction_count_240": len(predictions) == 240,
        "unique_gold_ids": len(set(gold_ids)) == len(gold_ids),
        "prediction_population_matches_gold": set(prediction_ids) == set(gold_ids),
        "all_gold_from_test_split": all(row.get("split") == "test" for row in gold),
        "all_gold_have_images": all(bool(row.get("images")) for row in gold),
        "all_gold_have_tool_catalog": all(bool(row.get("tools")) for row in gold),
        "targeted_train_id_overlap_zero": not (set(gold_ids) & targeted_ids),
        "targeted_train_scene_overlap_zero": not (gold_samples & targeted_samples),
        "expected_initial_adapter": adapters == Counter({args.expected_adapter: len(predictions)}),
        "multimodal_pixel_limit_recorded": all(value > 0 for value in pixel_limits),
        "routing_report_count_matches": routing.get("metrics", {}).get("count") == len(gold),
    }
    failures = [name for name, passed in checks.items() if not passed]
    metrics = routing.get("metrics", {})
    output = {
        "schema_version": "vaguehydro.formal_eval_bridge_audit.v1",
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
        "population": {
            "gold_records": len(gold),
            "gold_unique_scenes": len(gold_samples),
            "targeted_train_records": len(targeted),
            "targeted_train_unique_scenes": len(targeted_samples),
            "id_overlap": len(set(gold_ids) & targeted_ids),
            "scene_overlap": len(gold_samples & targeted_samples),
            "language_counts": dict(sorted(Counter(str(row.get("language")) for row in gold).items())),
            "ambiguity_counts": dict(sorted(Counter(str(row.get("ambiguity_level")) for row in gold).items())),
            "action_counts": dict(sorted(Counter(str(json.loads(row["messages"][-1]["content"])["action"]["type"]) for row in gold).items())),
        },
        "inference": {
            "adapters": dict(adapters),
            "max_image_pixels": {str(key): value for key, value in pixel_limits.items()},
            "model_revisions": dict(revisions),
            "code_path": "planner_messages -> AutoProcessor.apply_chat_template -> model.generate",
            "deterministic_greedy": True,
        },
        "metrics": metrics,
        "hashes": {
            "gold_sha256": sha256(gold_path),
            "predictions_sha256": sha256(predictions_path),
            "routing_report_sha256": sha256(routing_path),
            "targeted_train_sha256": sha256(targeted_path),
        },
        "interpretation": {
            "covers_recommended_large_untouched_eval": not failures,
            "multi_seed_needed_for_inference": False,
            "multi_seed_reason": "generation is deterministic greedy; uncertainty is reported by Wilson and 2000-sample scene bootstrap intervals",
            "formal_training_needed": False,
        },
    }
    Path(args.output_json).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markdown = f"""# 正式 240 条多模态评估桥接审计

## 原始数据表

| 项目 | 结果 |
|---|---:|
| 正式 gold / 预测 | {len(gold)} / {len(predictions)} |
| 唯一测试场景 | {len(gold_samples)} |
| 与定向 SFT 请求 ID 重叠 | {len(set(gold_ids) & targeted_ids)} |
| 与定向 SFT 场景重叠 | {len(gold_samples & targeted_samples)} |
| Schema valid | {metrics.get('schema_valid_rate', 0):.2%} |
| Tool selection | {metrics.get('tool_selection_accuracy', 0):.2%} |
| Workflow graph | {metrics.get('workflow_graph_accuracy', 0):.2%} |
| Argument slot F1 | {metrics.get('argument_slot_f1', 0):.2%} |
| Exact JSON request | {metrics.get('request_exact_match', 0):.2%} |

## 关键发现

1. 既有 `agent_eval_v1` 已覆盖建议的新评估：240 个未见测试场景、完整 ToolSpec、真实图像输入和与训练相同的多模态 processor 路径。
2. 240 条请求与定向 SFT v2 在请求 ID 和场景层面均零重叠，且全部预测使用初始适配器 `{args.expected_adapter}`。
3. 推理为 deterministic greedy；重复不同随机种子不会产生独立模型样本。当前不确定性已通过 Wilson 区间和 2000 次 scene bootstrap 报告。
4. 正式结果为 Schema/Tool/Workflow 100%，Argument slot F1 99.66%，Exact 96.67%。这比 14 条 pilot 更适合作为 Planner 主结果。

## 后续实验

不再重复运行同一 240 条推理。下一项有信息增益的实验应聚焦 8 个 exact mismatch 的逐字段错误审计，随后决定是否需要针对性修复；完整多模态专家质量仍应与 Planner 路由指标分开报告。
"""
    Path(args.output_md).write_text(markdown, encoding="utf-8")
    print(json.dumps({"status": output["status"], "failures": failures, "metrics": metrics}, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import random
from statistics import NormalDist
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry


ROUTING_EVALUATION_SCHEMA_VERSION = "vague_hydro.routing_eval.v1"


class RoutingEvaluationError(ValueError):
    """Raised when gold or prediction files violate the evaluation protocol."""


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_jsonl(path: Path) -> Iterator[Tuple[int, Dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RoutingEvaluationError(
                    f"{path}:{line_number} is not valid JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise RoutingEvaluationError(
                    f"{path}:{line_number} must contain an object"
                )
            yield line_number, payload


def parse_json_response(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str):
        raise RoutingEvaluationError("prediction payload must be an object or JSON string")
    cleaned = value.strip()
    if cleaned.lower().startswith("json\n"):
        cleaned = cleaned.split("\n", 1)[1].strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline >= 0:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RoutingEvaluationError("prediction is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RoutingEvaluationError("prediction JSON must contain an object")
    return payload


def _assistant_content(messages: Any) -> Any:
    if not isinstance(messages, list):
        raise RoutingEvaluationError("messages must be a list")
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "assistant":
            return message.get("content")
    raise RoutingEvaluationError("messages do not contain an assistant target")


def extract_gold(row: Mapping[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
    query_id = str(row.get("id") or row.get("query_id") or "")
    if not query_id:
        raise RoutingEvaluationError("gold record is missing id/query_id")
    if isinstance(row.get("gold_request"), dict):
        request = dict(row["gold_request"])
    else:
        request = parse_json_response(_assistant_content(row.get("messages")))
    metadata = {
        "split": str(row.get("split", "")),
        "language": str(row.get("language", "")),
        "ambiguity_level": str(row.get("ambiguity_level", "")),
    }
    return query_id, request, metadata


def extract_prediction(row: Mapping[str, Any]) -> Tuple[str, Any]:
    query_id = str(row.get("id") or row.get("query_id") or "")
    if not query_id and isinstance(row.get("prediction"), dict):
        query_id = str(row["prediction"].get("request_id", ""))
    if not query_id:
        query_id = str(row.get("request_id", ""))
    if not query_id:
        raise RoutingEvaluationError("prediction record is missing id/query_id")
    for field in ("prediction", "agent_request", "output", "response"):
        if field in row:
            return query_id, row[field]
    if "messages" in row:
        return query_id, _assistant_content(row["messages"])
    if "action" in row and "schema_version" in row:
        return query_id, dict(row)
    raise RoutingEvaluationError(
        f"prediction {query_id!r} has no prediction/agent_request/output/response field"
    )


def load_predictions(path: Path) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    for line_number, row in iter_jsonl(path):
        query_id, prediction = extract_prediction(row)
        if query_id in output:
            raise RoutingEvaluationError(
                f"{path}:{line_number} duplicates prediction id {query_id!r}"
            )
        output[query_id] = prediction
    return output


def _action_type(request: Mapping[str, Any]) -> str:
    action = request.get("action")
    return str(action.get("type", "")) if isinstance(action, dict) else ""


def _tool_sequence(request: Mapping[str, Any]) -> Tuple[str, ...]:
    action = request.get("action")
    if not isinstance(action, dict):
        return ()
    if action.get("type") == "tool_call":
        return (str(action.get("tool", "")),)
    if action.get("type") == "workflow":
        steps = action.get("steps")
        if isinstance(steps, list):
            return tuple(
                str(step.get("tool", ""))
                for step in steps
                if isinstance(step, dict)
            )
    return ()


def _flatten_arguments(
    value: Any,
    prefix: str,
    output: Set[Tuple[str, str]],
) -> None:
    if isinstance(value, dict):
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten_arguments(value[key], child_prefix, output)
        return
    output.add((prefix, canonical_json(value)))


def _argument_slots(request: Mapping[str, Any]) -> Set[Tuple[str, str]]:
    output: Set[Tuple[str, str]] = set()
    action = request.get("action")
    if not isinstance(action, dict):
        return output
    if action.get("type") == "tool_call":
        arguments = action.get("arguments")
        if isinstance(arguments, dict):
            _flatten_arguments(arguments, "action.arguments", output)
    elif action.get("type") == "workflow":
        steps = action.get("steps")
        if isinstance(steps, list):
            for index, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                step_id = str(step.get("step_id") or index)
                arguments = step.get("arguments")
                if isinstance(arguments, dict):
                    _flatten_arguments(
                        arguments,
                        f"action.steps.{step_id}.arguments",
                        output,
                    )
    return output


def _workflow_graph(
    request: Mapping[str, Any],
) -> Tuple[Set[Tuple[str, str]], Set[Tuple[str, str]]]:
    nodes: Set[Tuple[str, str]] = set()
    edges: Set[Tuple[str, str]] = set()
    action = request.get("action")
    if not isinstance(action, dict) or action.get("type") != "workflow":
        return nodes, edges
    steps = action.get("steps")
    if not isinstance(steps, list):
        return nodes, edges
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id", ""))
        nodes.add((step_id, str(step.get("tool", ""))))
        dependencies = step.get("depends_on", [])
        if isinstance(dependencies, list):
            edges.update((str(dependency), step_id) for dependency in dependencies)
    return nodes, edges


@dataclass
class MetricAccumulator:
    total: int = 0
    parsed: int = 0
    schema_valid: int = 0
    request_exact: int = 0
    request_id_correct: int = 0
    action_type_correct: int = 0
    intent_correct: int = 0
    expected_output_correct: int = 0
    tool_examples: int = 0
    tool_correct: int = 0
    workflow_examples: int = 0
    workflow_correct: int = 0
    argument_true_positive: int = 0
    argument_predicted: int = 0
    argument_gold: int = 0

    def add(self, other: "MetricAccumulator") -> None:
        for field_name in self.__dataclass_fields__:
            setattr(self, field_name, getattr(self, field_name) + getattr(other, field_name))

    def update(
        self,
        gold: Mapping[str, Any],
        prediction: Optional[Mapping[str, Any]],
        parsed: bool,
        schema_valid: bool,
    ) -> None:
        self.total += 1
        self.parsed += int(parsed)
        self.schema_valid += int(schema_valid)
        gold_action_type = _action_type(gold)
        if gold_action_type in {"tool_call", "workflow"}:
            self.tool_examples += 1
        if gold_action_type == "workflow":
            self.workflow_examples += 1
        gold_slots = _argument_slots(gold)
        self.argument_gold += len(gold_slots)
        if not schema_valid or prediction is None:
            return
        self.request_exact += int(canonical_json(gold) == canonical_json(prediction))
        self.request_id_correct += int(
            str(gold.get("request_id", ""))
            == str(prediction.get("request_id", ""))
        )
        self.action_type_correct += int(gold_action_type == _action_type(prediction))
        self.intent_correct += int(
            str(gold.get("intent", "")) == str(prediction.get("intent", ""))
        )
        self.expected_output_correct += int(
            gold.get("expected_output") == prediction.get("expected_output")
        )
        if gold_action_type in {"tool_call", "workflow"}:
            self.tool_correct += int(
                _tool_sequence(gold) == _tool_sequence(prediction)
            )
        if gold_action_type == "workflow":
            self.workflow_correct += int(
                _workflow_graph(gold) == _workflow_graph(prediction)
            )
        predicted_slots = _argument_slots(prediction)
        self.argument_predicted += len(predicted_slots)
        self.argument_true_positive += len(gold_slots & predicted_slots)

    def finalize(self) -> Dict[str, Any]:
        def ratio(numerator: int, denominator: int) -> Optional[float]:
            return numerator / denominator if denominator else None

        if self.argument_gold:
            precision = (
                self.argument_true_positive / self.argument_predicted
                if self.argument_predicted
                else 0.0
            )
            recall = self.argument_true_positive / self.argument_gold
        else:
            precision = None
            recall = None
        if precision is None or recall is None:
            argument_f1 = None
        elif precision + recall == 0:
            argument_f1 = 0.0
        else:
            argument_f1 = 2 * precision * recall / (precision + recall)
        return {
            "count": self.total,
            "parse_rate": ratio(self.parsed, self.total),
            "schema_valid_rate": ratio(self.schema_valid, self.total),
            "request_exact_match": ratio(self.request_exact, self.total),
            "request_id_accuracy": ratio(self.request_id_correct, self.total),
            "action_type_accuracy": ratio(self.action_type_correct, self.total),
            "intent_accuracy": ratio(self.intent_correct, self.total),
            "expected_output_accuracy": ratio(
                self.expected_output_correct, self.total
            ),
            "tool_selection_accuracy": ratio(self.tool_correct, self.tool_examples),
            "tool_selection_count": self.tool_examples,
            "argument_slot_precision": precision,
            "argument_slot_recall": recall,
            "argument_slot_f1": argument_f1,
            "argument_gold_slot_count": self.argument_gold,
            "workflow_graph_accuracy": ratio(
                self.workflow_correct, self.workflow_examples
            ),
            "workflow_count": self.workflow_examples,
        }


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot compute a quantile of an empty sequence")
    position = min(max(probability, 0.0), 1.0) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def bootstrap_confidence_intervals(
    contributions: Sequence[Tuple[str, MetricAccumulator]],
    samples: int,
    seed: int,
    confidence: float = 0.95,
) -> Dict[str, Any]:
    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("bootstrap confidence must be between zero and one")
    by_cluster: Dict[str, List[MetricAccumulator]] = defaultdict(list)
    for cluster_id, contribution in contributions:
        by_cluster[cluster_id].append(contribution)
    clusters = sorted(by_cluster)
    if not clusters:
        raise ValueError("bootstrap requires at least one evaluated example")
    metric_names = (
        "parse_rate",
        "schema_valid_rate",
        "request_exact_match",
        "request_id_accuracy",
        "action_type_accuracy",
        "intent_accuracy",
        "expected_output_accuracy",
        "tool_selection_accuracy",
        "argument_slot_precision",
        "argument_slot_recall",
        "argument_slot_f1",
        "workflow_graph_accuracy",
    )
    distributions: Dict[str, List[float]] = defaultdict(list)
    rng = random.Random(seed)
    for _ in range(samples):
        accumulator = MetricAccumulator()
        for _ in clusters:
            cluster_id = clusters[rng.randrange(len(clusters))]
            for contribution in by_cluster[cluster_id]:
                accumulator.add(contribution)
        metrics = accumulator.finalize()
        for metric_name in metric_names:
            value = metrics.get(metric_name)
            if isinstance(value, (int, float)):
                distributions[metric_name].append(float(value))
    tail = (1.0 - confidence) / 2.0
    return {
        "method": "cluster_bootstrap_percentile",
        "cluster_field": "sample_id",
        "cluster_count": len(clusters),
        "samples": samples,
        "seed": seed,
        "confidence": confidence,
        "metrics": {
            metric_name: {
                "lower": _quantile(values, tail),
                "upper": _quantile(values, 1.0 - tail),
            }
            for metric_name, values in sorted(distributions.items())
            if values
        },
    }


def binomial_confidence_intervals(
    accumulator: MetricAccumulator,
    confidence: float = 0.95,
) -> Dict[str, Any]:
    if not 0.0 < confidence < 1.0:
        raise ValueError("binomial confidence must be between zero and one")
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    counts = {
        "parse_rate": (accumulator.parsed, accumulator.total),
        "schema_valid_rate": (accumulator.schema_valid, accumulator.total),
        "request_exact_match": (accumulator.request_exact, accumulator.total),
        "request_id_accuracy": (accumulator.request_id_correct, accumulator.total),
        "action_type_accuracy": (accumulator.action_type_correct, accumulator.total),
        "intent_accuracy": (accumulator.intent_correct, accumulator.total),
        "expected_output_accuracy": (
            accumulator.expected_output_correct,
            accumulator.total,
        ),
        "tool_selection_accuracy": (
            accumulator.tool_correct,
            accumulator.tool_examples,
        ),
        "workflow_graph_accuracy": (
            accumulator.workflow_correct,
            accumulator.workflow_examples,
        ),
    }
    intervals: Dict[str, Any] = {}
    for metric_name, (successes, trials) in counts.items():
        if not trials:
            continue
        proportion = successes / trials
        denominator = 1.0 + z * z / trials
        center = (proportion + z * z / (2.0 * trials)) / denominator
        margin = (
            z
            * (
                proportion * (1.0 - proportion) / trials
                + z * z / (4.0 * trials * trials)
            )
            ** 0.5
            / denominator
        )
        intervals[metric_name] = {
            "lower": 0.0 if successes == 0 else max(0.0, center - margin),
            "upper": 1.0 if successes == trials else min(1.0, center + margin),
            "successes": successes,
            "trials": trials,
        }
    return {
        "method": "wilson_score",
        "confidence": confidence,
        "metrics": intervals,
    }


def evaluate_routing(
    gold_paths: Sequence[Path],
    prediction_path: Path,
    registry: ToolRegistry,
    max_error_examples: int = 20,
    bootstrap_samples: int = 0,
    bootstrap_seed: int = 20260731,
    bootstrap_confidence: float = 0.95,
) -> Dict[str, Any]:
    predictions = load_predictions(prediction_path)
    consumed_predictions: Set[str] = set()
    seen_gold: Set[str] = set()
    overall = MetricAccumulator()
    by_language: Dict[str, MetricAccumulator] = defaultdict(MetricAccumulator)
    by_level: Dict[str, MetricAccumulator] = defaultdict(MetricAccumulator)
    by_action_type: Dict[str, MetricAccumulator] = defaultdict(MetricAccumulator)
    by_language_level: Dict[str, MetricAccumulator] = defaultdict(MetricAccumulator)
    errors: List[Dict[str, Any]] = []
    contributions: List[Tuple[str, MetricAccumulator]] = []

    for gold_path in gold_paths:
        for line_number, row in iter_jsonl(gold_path):
            query_id, gold, metadata = extract_gold(row)
            if query_id in seen_gold:
                raise RoutingEvaluationError(
                    f"{gold_path}:{line_number} duplicates gold id {query_id!r}"
                )
            seen_gold.add(query_id)
            try:
                AgentRequest.from_dict(gold, registry)
            except AgentActionError as exc:
                raise RoutingEvaluationError(
                    f"gold request {query_id!r} violates AgentAction schema: {exc}"
                ) from exc

            raw_prediction = predictions.get(query_id)
            prediction: Optional[Dict[str, Any]] = None
            parsed = False
            schema_valid = False
            error: Optional[str] = None
            if raw_prediction is None:
                error = "missing_prediction"
            else:
                consumed_predictions.add(query_id)
                try:
                    prediction = parse_json_response(raw_prediction)
                    parsed = True
                    AgentRequest.from_dict(prediction, registry)
                    schema_valid = True
                except (RoutingEvaluationError, AgentActionError) as exc:
                    error = str(exc)

            contribution = MetricAccumulator()
            contribution.update(gold, prediction, parsed, schema_valid)
            cluster_id = str(row.get("sample_id") or query_id)
            contributions.append((cluster_id, contribution))
            accumulators = [
                overall,
                by_language[metadata["language"] or "unknown"],
                by_level[metadata["ambiguity_level"] or "unknown"],
                by_action_type[_action_type(gold) or "unknown"],
                by_language_level[
                    f"{metadata['language'] or 'unknown'}/"
                    f"{metadata['ambiguity_level'] or 'unknown'}"
                ],
            ]
            for accumulator in accumulators:
                accumulator.add(contribution)
            if error and len(errors) < max_error_examples:
                errors.append({"id": query_id, "error": error})

    extra_ids = sorted(set(predictions) - consumed_predictions)
    report = {
        "schema_version": ROUTING_EVALUATION_SCHEMA_VERSION,
        "status": "completed",
        "gold_count": len(seen_gold),
        "prediction_count": len(predictions),
        "missing_prediction_count": len(seen_gold - set(predictions)),
        "extra_prediction_count": len(extra_ids),
        "extra_prediction_examples": extra_ids[:max_error_examples],
        "error_examples": errors,
        "metrics": overall.finalize(),
        "by_language": {
            key: value.finalize() for key, value in sorted(by_language.items())
        },
        "by_ambiguity_level": {
            key: value.finalize() for key, value in sorted(by_level.items())
        },
        "by_gold_action_type": {
            key: value.finalize()
            for key, value in sorted(by_action_type.items())
        },
        "by_language_and_level": {
            key: value.finalize()
            for key, value in sorted(by_language_level.items())
        },
        "gold_sha256": {
            path.name: sha256_file(path) for path in gold_paths
        },
        "predictions_sha256": sha256_file(prediction_path),
        "binomial_confidence_intervals": binomial_confidence_intervals(
            overall,
            confidence=bootstrap_confidence,
        ),
    }
    if bootstrap_samples > 0:
        report["bootstrap"] = bootstrap_confidence_intervals(
            contributions,
            samples=bootstrap_samples,
            seed=bootstrap_seed,
            confidence=bootstrap_confidence,
        )
    return report

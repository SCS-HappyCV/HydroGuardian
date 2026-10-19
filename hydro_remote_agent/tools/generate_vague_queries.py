from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from hydro_remote_agent.data.vague_generation import (
    GenerationCache,
    VagueGenerationError,
    build_generation_prompt,
    deduplicate_exact_queries,
    generation_input_fingerprint,
    materialize_variants,
    validate_generation_payload,
)
from hydro_remote_agent.data.vague_hydro import audit_dataset, load_jsonl, write_jsonl
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _thinking_options(base_url: str) -> Dict[str, Any]:
    if "batch.dashscope.aliyuncs.com" in base_url:
        return {"enable_thinking": False}
    return {"chat_template_kwargs": {"enable_thinking": False}}


def _parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise VagueGenerationError("LLM response must be a JSON object")
    return payload


def _call_batch(
    records: Sequence[Mapping[str, Any]],
    language: str,
    args: argparse.Namespace,
) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    from openai import OpenAI

    api_key = args.api_key or os.getenv(args.api_key_env)
    if not api_key:
        raise EnvironmentError(f"Missing API key in {args.api_key_env}")
    client = OpenAI(
        api_key=api_key,
        base_url=args.base_url,
        timeout=float(args.timeout_seconds),
    )
    system_prompt, user_prompt = build_generation_prompt(records, language)
    last_error: Optional[Exception] = None
    try:
        for attempt in range(1, int(args.max_retries) + 1):
            try:
                response = client.chat.completions.create(
                    model=args.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=float(args.temperature),
                    max_tokens=int(args.max_output_tokens),
                    response_format={"type": "json_object"},
                    extra_body=_thinking_options(str(args.base_url)),
                )
                text = response.choices[0].message.content or ""
                payload = _parse_json_object(text)
                return (
                    validate_generation_payload(payload, records, language),
                    getattr(response, "id", None),
                )
            except Exception as exc:
                last_error = exc
                if attempt < int(args.max_retries):
                    time.sleep(min(2 ** (attempt - 1), 8))
    finally:
        client.close()
    assert last_error is not None
    raise last_error


def _select_records(
    records: Sequence[Mapping[str, Any]],
    limit_per_split: int,
) -> List[Dict[str, Any]]:
    if limit_per_split <= 0:
        return [dict(record) for record in records]
    counts = {"train": 0, "val": 0, "test": 0}
    selected = []
    for record in records:
        split = str(record["split"])
        if counts[split] >= limit_per_split:
            continue
        selected.append(dict(record))
        counts[split] += 1
    return selected


def _batches_by_split(
    records: Sequence[Mapping[str, Any]],
    batch_size: int,
) -> List[List[Dict[str, Any]]]:
    output: List[List[Dict[str, Any]]] = []
    for split in ("train", "val", "test"):
        split_records = [dict(record) for record in records if record["split"] == split]
        for index in range(0, len(split_records), batch_size):
            output.append(split_records[index : index + batch_size])
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate bilingual L0-L3 VagueHydro queries.")
    parser.add_argument(
        "--canonical-jsonl",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro" / "canonical_actions.jsonl"),
    )
    parser.add_argument(
        "--manifest-jsonl",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro" / "source_manifest.jsonl"),
    )
    parser.add_argument(
        "--registry",
        default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro_generated"),
    )
    parser.add_argument("--cache-path", default=None)
    parser.add_argument("--languages", nargs="+", default=["en", "zh"], choices=["en", "zh"])
    parser.add_argument("--limit-per-split", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model", default="qwen3.5-flash")
    parser.add_argument(
        "--base-url",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-output-tokens", type=int, default=5000)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.7)
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", default=None)
    pre_args, _ = pre_parser.parse_known_args(argv)
    parser = build_parser()
    if pre_args.config:
        with Path(pre_args.config).open("r", encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config, dict):
            raise ValueError("generation config must be a JSON object")
        parser.set_defaults(**config)
    parser.add_argument("--config", default=pre_args.config)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not args.api_key and not os.getenv(args.api_key_env):
        raise EnvironmentError(
            f"Missing API key in {args.api_key_env}; export it in the launch environment "
            "or pass --api-key without storing the value in a config file."
        )
    canonical = _select_records(load_jsonl(args.canonical_jsonl), args.limit_per_split)
    manifest = load_jsonl(args.manifest_jsonl)
    registry = load_tool_registry(args.registry)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path(args.cache_path) if args.cache_path else output_dir / "generation_cache.sqlite"
    cache = GenerationCache(cache_path)
    generated: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    cache_entry_count = 0

    try:
        pending_jobs = []
        for language in args.languages:
            uncached = []
            for record in canonical:
                cached = cache.get(
                    str(record["query_id"]),
                    language,
                    args.model,
                    generation_input_fingerprint(record),
                )
                if cached is None:
                    uncached.append(record)
                else:
                    generated.extend(
                        materialize_variants(
                            record,
                            cached["item"],
                            language,
                            args.model,
                            cached["response_id"],
                        )
                    )
            pending_jobs.extend(
                (batch, language)
                for batch in _batches_by_split(uncached, max(int(args.batch_size), 1))
            )

        with ThreadPoolExecutor(max_workers=max(int(args.workers), 1)) as executor:
            future_map = {
                executor.submit(_call_batch, batch, language, args): (batch, language)
                for batch, language in pending_jobs
            }
            completed = 0
            for future in as_completed(future_map):
                batch, language = future_map[future]
                try:
                    items, response_id = future.result()
                    for record in batch:
                        parent_id = str(record["query_id"])
                        item = items[parent_id]
                        cache.set(
                            parent_id,
                            language,
                            args.model,
                            item,
                            response_id,
                            generation_input_fingerprint(record),
                        )
                        generated.extend(
                            materialize_variants(
                                record,
                                item,
                                language,
                                args.model,
                                response_id,
                            )
                        )
                except Exception as exc:
                    parent_ids = ",".join(str(record["query_id"]) for record in batch)
                    print(
                        f"[Generate][batch-failed] language={language} "
                        f"parents={parent_ids} error={exc}"
                    )
                    failures.extend(
                        {
                            "parent_query_id": str(record["query_id"]),
                            "language": language,
                            "error": str(exc),
                        }
                        for record in batch
                    )
                completed += 1
                if completed <= 4 or completed % 10 == 0 or completed == len(pending_jobs):
                    print(
                        f"[Generate] batches={completed}/{len(pending_jobs)} "
                        f"records={len(generated)} failures={len(failures)} cache={cache.count()}"
                    )
        cache_entry_count = cache.count()
    finally:
        cache.close()

    generated, dedup_report = deduplicate_exact_queries(generated)
    generated.sort(key=lambda record: str(record["query_id"]))
    audit_report = audit_dataset(manifest, generated, registry)
    write_jsonl(output_dir / "vague_hydro_generated.jsonl", generated)
    for split in ("train", "val", "test"):
        write_jsonl(
            output_dir / f"vague_hydro_{split}.jsonl",
            (record for record in generated if record["split"] == split),
        )
    report = {
        "status": "passed" if not failures else "partial",
        "selected_parent_count": len(canonical),
        "generated_count": len(generated),
        "failure_count": len(failures),
        "failure_examples": failures[:20],
        "cache_entry_count": cache_entry_count,
        "deduplication": dedup_report,
        "action_audit": audit_report,
    }
    with (output_dir / "generation_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    if failures:
        write_jsonl(output_dir / "generation_failures.jsonl", failures)
        raise RuntimeError(f"{len(failures)} parent-language generations failed")
    stale_failure_path = output_dir / "generation_failures.jsonl"
    if stale_failure_path.exists():
        stale_failure_path.unlink()
    print(
        f"VAGUE_QUERY_GENERATION_OK parents={len(canonical)} generated={len(generated)} "
        f"output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

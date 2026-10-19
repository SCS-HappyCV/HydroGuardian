# VagueHydro Data

This directory contains deterministic Agent supervision derived from the WCS
image-point-language annotations. It is intentionally built before any LLM
paraphrase generation.

## Build

```powershell
python -m hydro_remote_agent.tools.build_vague_hydro `
  --output-dir hydro_remote_agent\data\vague_hydro `
  --path-map "/data/wcs10m=E:/dataset/point-image-text/10M" `
  --require-assets
```

The builder:

1. applies the frozen `1145/246/245` tile split;
2. normalizes source judgement semantics into unambiguous `direct_answer` queries while
   retaining the original wording in provenance;
3. derives explicit dense requests with tool or workflow actions;
4. validates every action against the deployment ToolSpecs;
5. checks asset availability and reports exact query collisions across splits.

## Outputs

- `source_manifest.jsonl`: one record per tile.
- `canonical_actions.jsonl`: all deterministic Agent supervision.
- `canonical_{train,val,test}.jsonl`: split-specific views.
- `audit_report.json`: action, split, asset, and leakage checks.
- `dataset_stats.json`: compact counts for experiment configuration.

The canonical files are not yet the final SFT dataset. Source text contains
cross-split template reuse. L0-L3 generation must use split-specific prompt
families, semantic deduplication, and a frozen evaluation set before training.

## L0-L3 Generation

The bilingual generator removes asset paths and tool names from its prompts,
requires the model to echo the frozen semantic signature, validates all four
ambiguity levels, and stores accepted responses in SQLite for safe resume.

```bash
export DASHSCOPE_API_KEY="..."
python -m hydro_remote_agent.tools.generate_vague_queries \
  --config hydro_remote_agent/configs/generate_vague_hydro_qwen35_flash.json
```

Run a balanced online pilot before full generation:

```bash
python -m hydro_remote_agent.tools.generate_vague_queries \
  --config hydro_remote_agent/configs/generate_vague_hydro_qwen35_flash.json \
  --limit-per-split 2 \
  --batch-size 2
```

Never write API keys into repository configs, shell scripts, generated records,
or tmux logs.

## Freeze and SFT

Freeze only after `generation_report.json` reports `passed` with zero failures:

```bash
python -m hydro_remote_agent.tools.freeze_vague_hydro \
  --provenance-file hydro_remote_agent/configs/generate_vague_hydro_qwen35_flash_batch_chat.json \
  --provenance-file hydro_remote_agent/data/vague_generation.py
```

The freeze manifest records SHA-256 hashes for the combined data, three split
files, generation report, source manifest, ontology, ToolSpec registry, and
generation provenance.

Convert the frozen records into `messages + tools` SFT examples:

```bash
python -m hydro_remote_agent.tools.format_vague_hydro_sft \
  --config hydro_remote_agent/configs/format_vague_hydro_sft.json
```

Each SFT record contains the strict AgentRequest target, stable six-tool
catalog, image paths for multimodal loading, point-cloud asset references, and
split/language/ambiguity metadata. The formatter rewrites legacy server path
prefixes using configured `path_map` entries and rejects any tile overlap
across train, validation, and test.

## Offline Routing Evaluation

Model predictions use one JSON object per line:

```json
{"id": "query-id", "prediction": {"schema_version": "1.0", "request_id": "query-id", "intent": "...", "action": {}, "expected_output": {}}}
```

Evaluate predictions against either generated records or SFT records:

```bash
python -m hydro_remote_agent.tools.evaluate_agent_routing \
  --gold hydro_remote_agent/data/vague_hydro_sft/test_sft.jsonl \
  --predictions runs/hydro_remote_agent/predictions/test_predictions.jsonl \
  --output runs/hydro_remote_agent/evaluation/test_report.json
```

The frozen metrics are parse rate, Schema Valid Rate, request ID accuracy,
request exact match, Action Type Accuracy, Intent Accuracy, Expected Output
Accuracy, Tool Selection Accuracy, Argument Slot micro-F1, and Workflow Graph
Accuracy. Reports include English/Chinese, L0-L3, and combined language-level
breakdowns. Missing or invalid predictions score zero rather than being
silently excluded.

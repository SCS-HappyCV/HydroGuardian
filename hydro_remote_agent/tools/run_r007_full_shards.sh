#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=/workspace/HydroGuardian
RUN_DIR="$PROJECT_ROOT/runs/hydro_remote_agent/expert_replacement_v1/r007_ptv3_full_test_20260820"
PYTHON=python
EVALUATOR="$PROJECT_ROOT/hydro_remote_agent/tools/evaluate_gufnet_segmentation.py"
RUNTIME="$PROJECT_ROOT/hydro_remote_agent/configs/expert_runtime.pointcept_ptv3.yaml"
SPLIT=/data/wcs10m/splits/wcs10m_primary/test.jsonl
DATA_ROOT=/workspace/HydroGuardian/benchmark/10M

mkdir -p "$RUN_DIR"
cd "$PROJECT_ROOT"

run_shard() {
  local start=$1
  local limit=$2
  local name=$3
  CUDA_VISIBLE_DEVICES=5 "$PYTHON" "$EVALUATOR" \
    --runtime "$RUNTIME" \
    --split "$SPLIT" \
    --data-root "$DATA_ROOT" \
    --start "$start" \
    --limit "$limit" \
    --output "$RUN_DIR/$name.jsonl" \
    --report "$RUN_DIR/${name}_report.json" \
    > "$RUN_DIR/${name}.log" 2>&1
}

run_shard 108 23 shard_109_131 &
pid_a=$!
run_shard 131 22 shard_132_153 &
pid_b=$!
run_shard 157 21 shard_158_178 &
pid_c=$!
run_shard 178 21 shard_179_199 &
pid_d=$!

wait "$pid_a"
wait "$pid_b"
wait "$pid_c"
wait "$pid_d"

cat \
  "$RUN_DIR/results.jsonl" \
  "$RUN_DIR/shard_107_153.jsonl" \
  "$RUN_DIR/shard_109_131.jsonl" \
  "$RUN_DIR/shard_132_153.jsonl" \
  "$RUN_DIR/shard_154_199.jsonl" \
  "$RUN_DIR/shard_158_178.jsonl" \
  "$RUN_DIR/shard_179_199.jsonl" \
  "$RUN_DIR/shard_200_245.jsonl" \
  > "$RUN_DIR/merged_results.jsonl"

"$PYTHON" - "$RUN_DIR/merged_results.jsonl" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    rows = [json.loads(line) for line in handle if line.strip()]
ids = [str(row["sample_id"]) for row in rows]
if len(rows) != 245 or len(set(ids)) != 245:
    raise SystemExit(f"Invalid merge: rows={len(rows)} unique_ids={len(set(ids))}")
print("R007_MERGE_VALID rows=245 unique_ids=245", flush=True)
PY

CUDA_VISIBLE_DEVICES=5 "$PYTHON" "$EVALUATOR" \
  --runtime "$RUNTIME" \
  --split "$SPLIT" \
  --data-root "$DATA_ROOT" \
  --output "$RUN_DIR/merged_results.jsonl" \
  --report "$RUN_DIR/report.json"

echo "R007_FULL_TEST_DONE report=$RUN_DIR/report.json"

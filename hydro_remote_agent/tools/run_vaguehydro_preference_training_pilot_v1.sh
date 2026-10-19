#!/usr/bin/env bash
set +e
cd /workspace/HydroGuardian || exit 90
export CUDA_VISIBLE_DEVICES=3
export PYTHONPATH=.
RUN_DIR=runs/hydro_remote_agent/vaguehydro_preference_training_pilot_v1
python \
  hydro_remote_agent/tools/launch_vaguehydro_preference_training_pilot_v1.py \
  --run-dir "$RUN_DIR" \
  > "$RUN_DIR/pilot.stdout.log" \
  2> "$RUN_DIR/pilot.stderr.log"
code=$?
printf '%s\n' "$code" > "$RUN_DIR/pilot.exit_code"
exit "$code"

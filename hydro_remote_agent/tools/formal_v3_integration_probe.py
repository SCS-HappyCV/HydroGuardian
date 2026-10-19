from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

from trl import GRPOConfig, GRPOTrainer

try:
    from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v3 import bind_trl_classes
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v3 import bind_trl_classes


def main() -> int:
    config_params = inspect.signature(GRPOConfig.__init__).parameters
    required = {"eval_strategy", "eval_steps", "save_strategy", "save_steps"}
    missing = sorted(required - set(config_params))
    BoundTrainer, Callback = bind_trl_classes(GRPOTrainer, __import__("transformers").TrainerCallback)
    result = {
        "trl_version": __import__("trl").__version__,
        "grpo_config_eval_save_parameters": sorted(required & set(config_params)),
        "missing_parameters": missing,
        "bound_trainer_name": BoundTrainer.__name__,
        "callback_name": Callback.__name__,
        "status": "pass" if not missing else "blocked",
        "real_classes": True,
    }
    print(json.dumps(result, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from hydro_remote_agent.baselines.tool_observation_react import compact_execution_observation


def test_compact_execution_observation_keeps_real_artifacts_and_metrics() -> None:
    observation = compact_execution_observation({
        "status": "succeeded",
        "result": {
            "execution_mode": "expert_runtime",
            "outcome": "result",
            "required_tools": ["point_semantic_segmentation"],
            "terminal_artifacts": {"point_labels": "/tmp/labels.npz"},
            "workflow_result": {
                "steps": [{
                    "step_id": "segment",
                    "tool": "point_semantic_segmentation",
                    "status": "succeeded",
                    "result": {
                        "metrics": {"point_count": 12},
                        "artifacts": {"point_labels": "/tmp/labels.npz"},
                    },
                    "verification_result": {
                        "metrics": {"verdict": "pass"},
                    },
                }],
            },
        },
    })
    assert observation["terminal_artifacts"]["point_labels"] == "/tmp/labels.npz"
    assert observation["steps"][0]["metrics"]["point_count"] == 12
    assert observation["steps"][0]["verification"]["verdict"] == "pass"

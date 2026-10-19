from hydro_remote_agent.tools.freeze_cmge_capability_policy import decide_policy


def _report(overall, class_iou, attribute_iou, complete):
    return {
        "conditions": {
            "claimwise_rule_decomposition": {
                "dense": {
                    "macro_iou": overall,
                    "by_intent_macro_iou": {
                        "class_segmentation": class_iou,
                        "attribute_segmentation": attribute_iou,
                    },
                },
                "complete_request_correctness_iou_0_5": complete,
            }
        }
    }


def test_freezes_when_overall_and_subgroups_pass():
    result = decide_policy(_report(.3, .2, .4, .25), _report(.6, .55, .65, .65), .02, .02)
    assert result["passed"] is True
    assert result["decision"] == "freeze_source_capability_policy"


def test_rejects_hidden_subgroup_regression():
    result = decide_policy(_report(.3, .2, .4, .25), _report(.4, .55, .37, .5), .02, .02)
    assert result["passed"] is False

from __future__ import annotations

import pytest

from hydro_remote_agent.backbones.external_vlm import (
    AllowedTokensLogitsProcessor,
    agent_request_json_schema,
    adapt_messages_for_family,
    cap_image_processor_pixels,
    extract_system_prompt,
    render_assistant_prefix,
    resize_image_to_pixel_budget,
)


def test_glm4v_message_adapter_preserves_text_and_uses_url() -> None:
    source = [
        {"role": "system", "content": [{"type": "text", "text": "system"}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": "/data/tile.png"},
                {"type": "text", "text": "query"},
            ],
        },
    ]
    adapted = adapt_messages_for_family(source, "glm4v")
    assert adapted[1]["content"][0] == {"type": "image", "url": "/data/tile.png"}
    assert adapted[1]["content"][1]["text"] == "query"
    assert source[1]["content"][0]["image"] == "/data/tile.png"


def test_external_message_adapter_rejects_unknown_family() -> None:
    with pytest.raises(ValueError, match="Unsupported external VLM"):
        adapt_messages_for_family([], "qwen")


def test_deepseek_vl2_adapter_preserves_system_and_image_order() -> None:
    source = [
        {"role": "system", "content": [{"type": "text", "text": "tools"}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": "/data/a.png"},
                {"type": "image", "image": "/data/b.png"},
                {"type": "text", "text": "query"},
            ],
        },
    ]
    adapted = adapt_messages_for_family(source, "deepseek_vl2")
    assert adapted == [
        {
            "role": "<|User|>",
            "content": "<image>\n<image>\nquery",
            "images": ["/data/a.png", "/data/b.png"],
        },
        {"role": "<|Assistant|>", "content": ""},
    ]
    assert extract_system_prompt(source) == "tools"


def test_deepseek_vl2_adapter_supports_json_assistant_prefix() -> None:
    source = [
        {"role": "system", "content": [{"type": "text", "text": "tools"}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": "/data/a.png"},
                {"type": "text", "text": "query"},
            ],
        },
    ]
    adapted = adapt_messages_for_family(source, "deepseek_vl2", assistant_prefix="{")
    assert adapted[-1] == {"role": "<|Assistant|>", "content": "{"}


def test_deepseek_vl2_renders_request_id_into_schema_prefix() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": "/data/a.png"},
                {"type": "text", "text": '{"request_id":"q:01"}'},
            ],
        }
    ]
    prefix = render_assistant_prefix(
        messages,
        "",
        '{"schema_version":"1.0","request_id":"{request_id}","intent":',
    )
    assert prefix == '{"schema_version":"1.0","request_id":"q:01","intent":'


def test_agent_request_constraint_requires_contract_and_action_union() -> None:
    schema = agent_request_json_schema("q:01")
    assert schema["properties"]["request_id"]["enum"] == ["q:01"]
    assert schema["required"] == [
        "schema_version",
        "request_id",
        "intent",
        "action",
        "expected_output",
    ]
    assert set(schema["properties"]["action"]["properties"]["type"]["enum"]) == {
        "direct_answer",
        "tool_call",
        "workflow",
        "clarification",
        "abstain",
    }


def test_allowed_tokens_processor_supports_empty_inputs_embeds_sequence() -> None:
    torch = pytest.importorskip("torch")
    class Tokenizer:
        eos_token_id = 3

        @staticmethod
        def decode(_tokens, skip_special_tokens=True):
            return "{}"

    processor = AllowedTokensLogitsProcessor(lambda _batch, sent: [1, 3], Tokenizer())
    scores = torch.tensor([[0.0, 1.0, 2.0, 3.0]])
    constrained = processor(torch.empty((1, 0), dtype=torch.long), scores)
    assert torch.isneginf(constrained[0, 0])
    assert constrained[0, 1].item() == 1.0
    assert torch.isneginf(constrained[0, 2])
    assert constrained[0, 3].item() == 3.0


def test_deepseek_image_resize_respects_area_and_aspect_ratio() -> None:
    pil = pytest.importorskip("PIL.Image")
    source = pil.new("RGB", (2000, 1000))
    resized = resize_image_to_pixel_budget(source, 262144)
    assert resized.width * resized.height <= 262144
    assert resized.width / resized.height == pytest.approx(2.0, rel=0.01)
    small = pil.new("RGB", (100, 50))
    unchanged = resize_image_to_pixel_budget(small, 262144)
    assert unchanged.size == (100, 50)
    assert unchanged is not small


def test_external_image_processor_is_capped_to_shared_budget() -> None:
    class ImageProcessor:
        size = {"shortest_edge": 12544, "longest_edge": 9633792}

    class Processor:
        image_processor = ImageProcessor()

    processor = Processor()
    cap_image_processor_pixels(processor, 262144)
    assert processor.image_processor.size == {
        "shortest_edge": 12544,
        "longest_edge": 262144,
    }


def test_external_size_object_is_capped_to_shared_budget() -> None:
    class Size:
        def __init__(self, shortest_edge: int, longest_edge: int) -> None:
            self.shortest_edge = shortest_edge
            self.longest_edge = longest_edge

    class ImageProcessor:
        size = Size(shortest_edge=12544, longest_edge=9633792)

    class Processor:
        image_processor = ImageProcessor()

    processor = Processor()
    cap_image_processor_pixels(processor, 262144)
    assert processor.image_processor.size.shortest_edge == 12544
    assert processor.image_processor.size.longest_edge == 262144

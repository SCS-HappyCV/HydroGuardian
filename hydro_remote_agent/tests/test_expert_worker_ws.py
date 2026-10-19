from __future__ import annotations

import pytest
from PIL import Image

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.expert_worker_ws import (
    configure_source_image_limit,
    select_capability_registry,
)


REGISTRY_PATH = "hydro_remote_agent/configs/tool_registry.yaml"


def test_configure_source_image_limit_raises_pillow_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Image.MAX_IMAGE_PIXELS
    try:
        monkeypatch.setenv("EXPERT_MAX_SOURCE_IMAGE_PIXELS", "350000000")
        assert configure_source_image_limit() == 350000000
        assert Image.MAX_IMAGE_PIXELS == 350000000
    finally:
        Image.MAX_IMAGE_PIXELS = original


def test_configure_source_image_limit_uses_large_raster_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Image.MAX_IMAGE_PIXELS
    try:
        monkeypatch.delenv("EXPERT_MAX_SOURCE_IMAGE_PIXELS", raising=False)
        assert configure_source_image_limit() == 350000000
        assert Image.MAX_IMAGE_PIXELS == 350000000
    finally:
        Image.MAX_IMAGE_PIXELS = original


def test_configure_source_image_limit_rejects_non_positive_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXPERT_MAX_SOURCE_IMAGE_PIXELS", "0")
    with pytest.raises(ValueError, match="must be positive"):
        configure_source_image_limit()


def test_select_capability_registry_keeps_only_requested_tools() -> None:
    registry = load_tool_registry(REGISTRY_PATH)

    selected = select_capability_registry(
        registry,
        ("geometry_relation_analysis", "result_quality_verification"),
    )

    assert selected.schema_version == registry.schema_version
    assert selected.names() == (
        "geometry_relation_analysis",
        "result_quality_verification",
    )


def test_select_capability_registry_rejects_unknown_capability() -> None:
    registry = load_tool_registry(REGISTRY_PATH)

    with pytest.raises(ValueError, match="Unknown worker capabilities"):
        select_capability_registry(registry, ("not_a_registered_tool",))


def test_select_capability_registry_rejects_duplicate_capability() -> None:
    registry = load_tool_registry(REGISTRY_PATH)

    with pytest.raises(ValueError, match="Duplicate worker capabilities"):
        select_capability_registry(
            registry,
            ("geometry_relation_analysis", "geometry_relation_analysis"),
        )

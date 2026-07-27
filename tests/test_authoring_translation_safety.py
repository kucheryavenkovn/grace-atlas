from __future__ import annotations

from pathlib import Path

import pytest

from grace_atlas.authoring.models import TranslationInput
from grace_atlas.authoring.settings import AuthoringSettings, LlmSettings, TranslationSettings
from grace_atlas.authoring.translation import build_translation_draft
from grace_atlas.model import AtlasGraph, Node, NodeType


class FakeLlm:
    provider = "fake"
    model = "fake-model"

    def generate_json(self, *, system: str, user: str) -> dict:
        return {
            "translations": {
                "name": "Run analysis",
                "description": "The user starts analysis",
            }
        }


def _settings(tmp_path: Path) -> AuthoringSettings:
    return AuthoringSettings(
        workspace=tmp_path / ".grace-atlas" / "authoring",
        allow_source_replace=True,
        llm=LlmSettings(provider="openai-compatible", model="fake"),
        translation=TranslationSettings(),
    )


def _graph() -> AtlasGraph:
    graph = AtlasGraph()
    graph.add_node(
        Node(
            id="UC-001",
            name="Запустить анализ",
            type=NodeType.USE_CASE,
            description="Пользователь запускает анализ",
            source="requirements",
        )
    )
    return graph


def test_source_replacement_requires_one_field_per_patch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one field per patch"):
        build_translation_draft(
            _graph(),
            TranslationInput(
                entity_id="UC-001",
                target_language="en",
                fields=("name", "description"),
                replace_source=True,
            ),
            settings=_settings(tmp_path),
            llm=FakeLlm(),
        )


def test_single_field_source_replacement_produces_update_property(tmp_path: Path) -> None:
    draft, patch = build_translation_draft(
        _graph(),
        TranslationInput(
            entity_id="UC-001",
            target_language="en",
            fields=("name",),
            replace_source=True,
        ),
        settings=_settings(tmp_path),
        llm=FakeLlm(),
    )
    assert draft.payload["translations"]["name"] == "Run analysis"
    assert patch is not None
    assert len(patch["operations"]) == 1
    assert patch["operations"][0]["operation"] == "update_property"
    assert patch["operations"][0]["property"] == "name"

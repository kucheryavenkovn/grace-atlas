from __future__ import annotations

import json
from pathlib import Path

from grace_atlas.authoring.context import build_entity_context
from grace_atlas.authoring.models import RequirementInput, TranslationInput
from grace_atlas.authoring.patching import plan_authoring_patch, validate_authoring_patch
from grace_atlas.authoring.requirements import build_requirement_draft
from grace_atlas.authoring.settings import AuthoringSettings, LlmSettings, TranslationSettings, render_settings_template
from grace_atlas.authoring.translation import build_translation_draft
from grace_atlas.config import AtlasConfig
from grace_atlas.model import AtlasGraph, Edge, Node, NodeType, Provenance, SourceRef


class FakeLlm:
    provider = "fake"
    model = "fake-model"

    def __init__(self, response: dict):
        self.response = response

    def generate_json(self, *, system: str, user: str) -> dict:
        assert system
        assert user
        return self.response


def _settings(tmp_path: Path, *, allow_source_replace: bool = False) -> AuthoringSettings:
    return AuthoringSettings(
        workspace=tmp_path / ".grace-atlas" / "authoring",
        allow_source_replace=allow_source_replace,
        llm=LlmSettings(provider="openai-compatible", model="fake"),
        translation=TranslationSettings(),
    )


def _graph(tmp_path: Path) -> AtlasGraph:
    graph = AtlasGraph()
    graph.add_node(
        Node(
            id="UC-001",
            name="Запустить анализ",
            type=NodeType.USE_CASE,
            description="Пользователь запускает анализ проекта",
            source="requirements",
            source_ref=SourceRef(path=str(tmp_path / "docs" / "requirements.xml"), line_start=3),
            properties={"actor": "User", "acceptance_criteria": "Результат сохранён"},
        )
    )
    graph.add_node(Node(id="M-ANALYZE", name="Analyze", type=NodeType.MODULE, description="Analysis module"))
    graph.add_edge(
        Edge(
            source="UC-001",
            target="M-ANALYZE",
            type="implemented_in",
            provenance=Provenance.DECLARED,
        )
    )
    return graph


def test_context_is_bounded_and_traceable(tmp_path: Path) -> None:
    context = build_entity_context(_graph(tmp_path), ["UC-001"], depth=1, max_nodes=10)
    assert context["roots"] == ["UC-001"]
    assert {node["id"] for node in context["nodes"]} == {"UC-001", "M-ANALYZE"}
    assert context["edges"][0]["relation"] == "implemented_in"


def test_translation_creates_sidecar_draft_without_patch_by_default(tmp_path: Path) -> None:
    draft, patch = build_translation_draft(
        _graph(tmp_path),
        TranslationInput(entity_id="UC-001", target_language="en"),
        settings=_settings(tmp_path),
        llm=FakeLlm(
            {"translations": {"name": "Run analysis", "description": "The user starts project analysis"}}
        ),
    )
    assert patch is None
    assert draft.payload["translations"]["name"] == "Run analysis"
    assert draft.evidence[0].entity_id == "UC-001"


def test_requirement_draft_compiles_create_and_trace_operations(tmp_path: Path) -> None:
    draft, patch = build_requirement_draft(
        _graph(tmp_path),
        RequirementInput(evidence_ids=("M-ANALYZE",), requirement_id="UC-AUTH-001", use_llm=True),
        settings=_settings(tmp_path),
        llm=FakeLlm(
            {
                "title": "Analyze project",
                "actor": "User",
                "action": "Starts analysis",
                "goal": "Receive a traceable analysis result",
                "priority": "high",
                "preconditions": ["Project exists"],
                "acceptanceCriteria": ["Analysis result is persisted"],
                "relatedFlows": [],
            }
        ),
    )
    assert draft.payload["requirementId"] == "UC-AUTH-001"
    assert patch["operations"][0]["operation"] == "create_use_case"
    assert patch["operations"][1]["operation"] == "add_edge"
    assert patch["operations"][1]["target"] == "M-ANALYZE"


def _project(tmp_path: Path) -> AtlasConfig:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "requirements.xml").write_text(
        """<RequirementsAnalysis>
  <UseCases>
    <UC-001>
      <Actor>User</Actor>
      <Action>Analyze</Action>
      <Goal>Result</Goal>
      <Priority>high</Priority>
      <Preconditions>Project exists</Preconditions>
      <AcceptanceCriteria>Result saved</AcceptanceCriteria>
      <RelatedFlows></RelatedFlows>
    </UC-001>
  </UseCases>
</RequirementsAnalysis>
""",
        encoding="utf-8",
    )
    (docs / "knowledge-graph.xml").write_text(
        "<KnowledgeGraph>\n  <CrossLinks>\n  </CrossLinks>\n</KnowledgeGraph>\n",
        encoding="utf-8",
    )
    return AtlasConfig(
        repo_root=tmp_path,
        search_paths=["docs"],
        artifact_overrides={
            "requirements": "docs/requirements.xml",
            "knowledge_graph": "docs/knowledge-graph.xml",
        },
    )


def test_authoring_patch_plans_and_validates_new_use_case(tmp_path: Path) -> None:
    config = _project(tmp_path)
    patch_file = tmp_path / "proposal.json"
    patch_file.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "patchId": "patch-1",
                "operations": [
                    {
                        "operation": "create_use_case",
                        "entityId": "UC-AUTH-002",
                        "value": {
                            "actor": "Analyst",
                            "action": "Reviews traceability",
                            "goal": "Find gaps",
                            "priority": "high",
                            "preconditions": ["Atlas built"],
                            "acceptanceCriteria": ["Gaps are listed"],
                            "relatedFlows": [],
                        },
                    },
                    {
                        "operation": "add_edge",
                        "source": "UC-AUTH-002",
                        "target": "UC-001",
                        "relation": "refers_to",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    plan = plan_authoring_patch(config, patch_file)
    assert plan.ok, plan.errors
    assert {change.action for change in plan.changes} == {
        "insert_before_usecases_close",
        "insert_before_crosslinks_close",
    }
    validation = validate_authoring_patch(config, patch_file)
    assert validation["ok"], validation
    assert validation["missingCreatedEntities"] == []


def test_settings_template_never_contains_secret_value() -> None:
    template = render_settings_template()
    assert "GRACE_ATLAS_API_KEY" in template
    assert "api_key =" not in template

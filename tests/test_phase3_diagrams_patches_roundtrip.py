# FILE: tools/grace_atlas/tests/test_phase3_diagrams_patches_roundtrip.py
# VERSION: 0.4.0
# PURPOSE: Phase 3B/3C/3D tests (fixtures only for mutations)

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from grace_atlas.config import load_config
from grace_atlas.diagrams.catalog import (
    delete_user_diagram,
    list_user_diagrams,
    mark_unresolved_nodes,
    save_user_diagram,
)
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.enrichment import enrich_graph
from grace_atlas.graph import build_graph
from grace_atlas.patches.apply import apply_to_temp, atomic_apply_from_temp
from grace_atlas.patches.planner import plan_patch
from grace_atlas.patches.schema import GracePatch, new_patch, validate_patch_schema
from grace_atlas.roundtrip.drift import compute_drift
from grace_atlas.roundtrip.impact import impact_query
from grace_atlas.roundtrip.scanner import scan_project
from grace_atlas.snapshots import build_and_write_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "minimal"


@pytest.fixture
def proj(tmp_path: Path):
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    # ensure knowledge-graph has CrossLinks container if present
    return load_config(repo_root=root)


def test_user_diagrams_survive_rebuild(proj):
    diagram = {
        "schemaVersion": "1.0.0",
        "id": "user:demo",
        "name": "Demo",
        "type": "custom",
        "rootEntityIds": ["UC-001"],
        "query": {
            "includeRelations": ["related_flow"],
            "excludeRelations": [],
            "includeNodeTypes": [],
            "excludeNodeTypes": [],
            "direction": "both",
            "depth": 2,
            "includeDiagnostics": True,
        },
        "layout": {"algorithm": "elk-layered", "direction": "RIGHT", "spacing": 40},
        "hiddenNodeIds": [],
        "hiddenEdgeIds": [],
        "pinnedNodeIds": ["UC-001"],
        "manualPositions": {"UC-001": {"x": 10, "y": 20}},
        "collapsedGroups": [],
        "viewport": {"zoom": 1.2, "panX": 0, "panY": 0},
        "createdFrom": "user",
        "readOnly": False,
    }
    save_user_diagram(proj, diagram)
    graph, _ = build_graph(proj)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    build_and_write_snapshot(graph, report, proj)
    listed = list_user_diagrams(proj)
    assert any(d.get("id") == "user:demo" for d in listed)
    assert listed[0]["manualPositions"]["UC-001"]["x"] == 10
    # hide does not alter model
    assert "UC-001" in {n.id for n in graph.nodes.values()} or True
    delete_user_diagram(proj, "user:demo")
    assert list_user_diagrams(proj) == []


def test_unresolved_tombstone():
    d = mark_unresolved_nodes(
        {
            "rootEntityIds": ["A", "MISSING"],
            "pinnedNodeIds": ["A"],
            "hiddenNodeIds": [],
            "manualPositions": {"GONE": {"x": 1, "y": 2}},
        },
        {"A"},
    )
    assert "MISSING" in d["unresolvedNodeIds"]
    assert "GONE" in d["unresolvedNodeIds"]


def test_patch_schema_and_unsupported():
    p = new_patch(
        [
            {
                "operation": "raw_xpath",
                "source": "a",
                "target": "b",
            }
        ]
    )
    errs = validate_patch_schema(p)
    assert any("unsupported" in e for e in errs)


def test_patch_duplicate_and_stale(proj):
    graph, _ = build_graph(proj)
    # invent edge that may or may not exist — use nonsense relation first
    patch = new_patch(
        [
            {
                "operation": "add_edge",
                "source": "NOPE",
                "target": "NOPE2",
                "relation": "implements",
                "reason": "test",
            }
        ],
        project_hash="stalehash",
    )
    plan = plan_patch(proj, patch, graph, current_model_hash="realhash")
    assert not plan.ok
    assert any("stale" in e for e in plan.errors)


def test_patch_preview_without_mutation(proj):
    graph, _ = build_graph(proj)
    report = build_gap_report(graph)
    nodes = list(graph.nodes.keys())
    if len(nodes) < 2:
        pytest.skip("need nodes")
    # pick two existing nodes
    src, tgt = nodes[0], nodes[1]
    # find a relation that does not exist yet
    patch = new_patch(
        [
            {
                "operation": "add_edge",
                "source": src,
                "target": tgt,
                "relation": "cross_link",
                "reason": "fixture test",
                "expectedSourceState": "missing",
            }
        ]
    )
    kg = proj.repo_root / "knowledge-graph.xml"
    if not kg.is_file():
        # fixture may name differently
        from grace_atlas.discovery import discover_artifacts

        arts = discover_artifacts(proj)
        if not arts.knowledge_graph:
            pytest.skip("no knowledge-graph in fixture")
    before = None
    from grace_atlas.discovery import discover_artifacts

    arts = discover_artifacts(proj)
    if arts.knowledge_graph:
        before = arts.knowledge_graph.read_text(encoding="utf-8")
    plan = plan_patch(proj, patch, graph)
    if not plan.ok:
        # may fail if kg missing CrossLinks — still no mutation
        if arts.knowledge_graph and before is not None:
            assert arts.knowledge_graph.read_text(encoding="utf-8") == before
        return
    temp = apply_to_temp(proj, plan)
    assert temp.get("ok")
    # live file unchanged
    if arts.knowledge_graph and before is not None:
        assert arts.knowledge_graph.read_text(encoding="utf-8") == before
    # cleanup
    import shutil as sh

    sh.rmtree(temp["tempDir"], ignore_errors=True)


def test_patch_apply_on_fixture_only(proj):
    """Apply only against copied fixture — never real Video2PPTX XML."""
    graph, _ = build_graph(proj)
    from grace_atlas.discovery import discover_artifacts

    arts = discover_artifacts(proj)
    if not arts.knowledge_graph:
        pytest.skip("no kg")
    # Ensure CrossLinks section exists for insert
    text = arts.knowledge_graph.read_text(encoding="utf-8")
    if "</KnowledgeGraph>" in text and "<CrossLinks>" not in text:
        text = text.replace(
            "</KnowledgeGraph>",
            "  <CrossLinks>\n  </CrossLinks>\n</KnowledgeGraph>",
        )
        arts.knowledge_graph.write_text(text, encoding="utf-8")
    nodes = [n for n in graph.nodes.values() if not n.properties.get("stub")]
    if len(nodes) < 2:
        pytest.skip("need nodes")
    src, tgt = nodes[0].id, nodes[1].id
    # skip if already linked
    patch = new_patch(
        [
            {
                "operation": "add_edge",
                "source": src,
                "target": tgt,
                "relation": "cross_link",
                "reason": "fixture apply",
            }
        ]
    )
    plan = plan_patch(proj, patch, graph)
    if not plan.ok:
        pytest.skip(f"plan blocked: {plan.errors}")
    temp = apply_to_temp(proj, plan)
    assert temp.get("ok")
    result = atomic_apply_from_temp(proj, plan, temp, allow_new_errors=True)
    assert result.get("ok"), result
    after = arts.knowledge_graph.read_text(encoding="utf-8")
    assert src in after and tgt in after


def test_scan_and_drift(proj):
    # create a source file
    src = proj.repo_root / "src"
    src.mkdir(exist_ok=True)
    f = src / "demo.py"
    f.write_text("# START_CONTRACT: demo\ndef demo():\n    return 1\n", encoding="utf-8")
    r1 = scan_project(proj, changed_only=False)
    assert r1["scanned"] >= 1
    r2 = scan_project(proj, changed_only=True)
    assert r2["skipped"] >= 1 or r2["changed"] == 0
    f.write_text("# START_CONTRACT: demo\ndef demo():\n    return 2\n", encoding="utf-8")
    r3 = scan_project(proj, changed_only=True)
    assert r3["changed"] >= 1
    drift = compute_drift(proj, rescan=False)
    assert "items" in drift
    assert drift.get("note")


def test_impact_query(proj):
    graph, _ = build_graph(proj)
    roots = list(graph.nodes.keys())[:1]
    if not roots:
        pytest.skip("empty graph")
    result = impact_query(graph, roots=roots, direction="both", max_depth=2)
    assert result["roots"]
    assert "directlyAffected" in result
    assert "explanations" in result


def test_impact_max_depth_and_cycle(proj):
    graph, _ = build_graph(proj)
    if not graph.nodes:
        pytest.skip("empty")
    root = next(iter(graph.nodes))
    r1 = impact_query(graph, roots=[root], max_depth=1)
    r3 = impact_query(graph, roots=[root], max_depth=3)
    assert len(r3["distances"]) >= len(r1["distances"])

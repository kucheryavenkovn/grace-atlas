# FILE: tools/grace_atlas/tests/test_snapshot.py
# VERSION: 0.4.0
# PURPOSE: Phase 3A workbench snapshot tests

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grace_atlas.config import load_config
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.enrichment import enrich_graph
from grace_atlas.graph import build_graph
from grace_atlas.snapshots import (
    SCHEMA_VERSION,
    build_and_write_snapshot,
    build_snapshot_bundle,
    inspect_entity,
    load_snapshot,
    model_dir_for,
    validate_snapshot_dir,
)
from grace_atlas.snapshots.schema import is_compatible_schema
from grace_atlas.snapshots.serializer import model_hash
from grace_atlas.snapshots.validator import SnapshotValidationError, validate_model


FIXTURE = Path(__file__).parent / "fixtures" / "minimal"


@pytest.fixture
def fixture_config(tmp_path: Path):
    # copy minimal fixture into tmp so writes don't pollute
    import shutil

    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    return load_config(repo_root=root)


def test_schema_compat():
    assert is_compatible_schema("1.0.0")
    assert is_compatible_schema("1.1.0") is False or is_compatible_schema("1.0.9")
    assert not is_compatible_schema("2.0.0")
    assert not is_compatible_schema("nope")


def test_deterministic_snapshot(fixture_config):
    graph, _ = build_graph(fixture_config, include_source=True)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    b1 = build_snapshot_bundle(graph, report, fixture_config, generated_at="FIXED")
    b2 = build_snapshot_bundle(graph, report, fixture_config, generated_at="FIXED")
    assert b1["model"] == b2["model"]
    assert b1["diagnostics"]["findings"] == b2["diagnostics"]["findings"]
    assert model_hash(b1["model"], b1["diagnostics"]) == model_hash(b2["model"], b2["diagnostics"])
    # generatedAt should not change content hash
    b3 = build_snapshot_bundle(graph, report, fixture_config, generated_at="OTHER")
    assert b1["manifest"]["modelHash"] == b3["manifest"]["modelHash"]


def test_stable_ids_and_sorted(fixture_config):
    graph, _ = build_graph(fixture_config, include_source=True)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    bundle = build_snapshot_bundle(graph, report, fixture_config)
    ids = [n["id"] for n in bundle["model"]["nodes"]]
    assert ids == sorted(ids)
    edge_ids = [e["id"] for e in bundle["model"]["edges"]]
    assert edge_ids == sorted(edge_ids)
    assert len(edge_ids) == len(set(edge_ids))
    assert all(e["id"] == f"{e['source']}|{e['relation']}|{e['target']}" for e in bundle["model"]["edges"])


def test_referential_integrity(fixture_config):
    graph, _ = build_graph(fixture_config, include_source=True)
    report = build_gap_report(graph)
    bundle = build_snapshot_bundle(graph, report, fixture_config)
    errors = validate_model(bundle["model"])
    assert errors == []


def test_indexes(fixture_config):
    graph, _ = build_graph(fixture_config, include_source=True)
    report = build_gap_report(graph)
    bundle = build_snapshot_bundle(graph, report, fixture_config)
    idx = bundle["indexes"]
    assert "nodeById" in idx
    assert "incomingByNode" in idx
    assert "outgoingByNode" in idx
    assert "nodesByType" in idx
    # every node id present
    for n in bundle["model"]["nodes"]:
        assert n["id"] in idx["nodeById"]


def test_atomic_write_and_load(fixture_config):
    graph, _ = build_graph(fixture_config, include_source=True)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    result = build_and_write_snapshot(graph, report, fixture_config)
    md = Path(result["model_dir"])
    assert (md / "manifest.json").is_file()
    assert (md / "model.json").is_file()
    assert (md / "schemas" / "workbench-model.schema.json").is_file()
    v = validate_snapshot_dir(md)
    assert v["ok"]
    data = load_snapshot(md)
    assert data["manifest"]["schemaVersion"] == SCHEMA_VERSION


def test_inspect_entity(fixture_config):
    graph, _ = build_graph(fixture_config, include_source=True)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    build_and_write_snapshot(graph, report, fixture_config)
    # pick first node
    data = load_snapshot(model_dir_for(fixture_config))
    eid = data["model"]["nodes"][0]["id"]
    info = inspect_entity(model_dir_for(fixture_config), eid)
    assert info["node"]["id"] == eid


def test_invalid_model_raises():
    with pytest.raises(SnapshotValidationError):
        from grace_atlas.snapshots.validator import validate_bundle

        validate_bundle({"schemaVersion": "9.0.0"}, {"schemaVersion": "9.0.0", "nodes": [], "edges": []})

# FILE: tools/grace_atlas/tests/test_unit_core.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Unit tests with minimal fixtures for Atlas v0.2 acceptance criteria.
#   ROLE: TEST
# END_MODULE_CONTRACT

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from grace_atlas.config import AtlasConfig, load_config
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.discovery import discover_artifacts
from grace_atlas.exporters.canvas import build_all_canvases, dumps_canvas, validate_canvas_file_refs
from grace_atlas.exporters.markdown import render_node_note
from grace_atlas.exporters.notes import file_note_stem, note_relpath, safe_filename, wikilink
from grace_atlas.exporters.obsidian import (
    VaultSafetyError,
    assert_safe_vault_path,
    export_vault,
    is_atlas_vault,
)
from grace_atlas.graph import build_graph
from grace_atlas.model import Node, NodeType
from grace_atlas.source_links import path_to_vscode_file_component, vscode_uri
from grace_atlas.trace import format_trace

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal"


def _fixture_config(tmp_path: Path | None = None) -> AtlasConfig:
    cfg = load_config(repo_root=FIXTURE, config_path=FIXTURE / "grace-atlas.toml")
    if tmp_path is not None:
        cfg.vault_path = tmp_path / "vault"
    return cfg


def test_discover_fixture_xml():
    cfg = _fixture_config()
    arts = discover_artifacts(cfg)
    assert arts.requirements is not None
    assert arts.knowledge_graph is not None
    assert arts.development_plan is not None
    assert arts.verification_plan is not None


def test_extract_ids_and_edges():
    cfg = _fixture_config()
    graph, _ = build_graph(cfg, include_source=True)
    assert graph.get("UC-001") is not None
    assert graph.get("M-CORE") is not None
    assert graph.get("V-M-CORE") is not None
    assert graph.get("Phase-2") is not None
    deps = [e for e in graph.edges if e.source == "M-HELPER" and e.type == "depends_on"]
    assert any(e.target == "M-CORE" for e in deps)
    impl = [e for e in graph.edges if e.source == "M-CORE" and e.type == "implemented_in"]
    assert impl


def test_broken_orphan_unverified():
    cfg = _fixture_config()
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    codes = {f.code for f in report.findings}
    assert "MISSING_FILE" in codes or "BROKEN_REFERENCE" in codes
    assert "ORPHAN_REQUIREMENT" in codes
    assert "UNVERIFIED_MODULE" in codes


def test_safe_filename_and_note_paths():
    assert ":" not in safe_filename("M:Weird")
    assert "/" not in safe_filename("a/b")
    assert file_note_stem("src/sample/core.py") == "src__sample__core.py"
    n = Node(id="M-CORE", name="Core", type=NodeType.MODULE)
    assert note_relpath(n) == "Modules/M-CORE.md"
    f = Node(
        id="file:src/sample/core.py",
        name="src/sample/core.py",
        type=NodeType.SOURCE_FILE,
        properties={"path": "src/sample/core.py"},
    )
    assert note_relpath(f) == "Source-Files/src__sample__core.py.md"
    link = wikilink(n, "M-CORE")
    assert "Modules/M-CORE" in link


def test_vscode_uri_encoding():
    encoded = path_to_vscode_file_component("C:/Users/tux/my project/file.py")
    assert encoded.startswith("/C:/")
    assert "%20" in encoded or " " not in encoded
    uri = vscode_uri("C:/tmp/foo.py", line=10, column=3)
    assert uri.startswith("vscode://file")
    assert uri.endswith(":10:3")
    uri2 = vscode_uri("C:/tmp/foo.py")
    assert uri2.startswith("vscode://file")
    # no trailing :line when unknown
    assert not uri2.endswith(":0")
    assert uri2.count(":") >= 2  # vscode + maybe drive


def test_wiki_links_in_note():
    cfg = _fixture_config()
    graph, _ = build_graph(cfg, include_source=False)
    node = graph.get("M-HELPER")
    assert node is not None
    md = render_node_note(node, graph, cfg)
    assert "generated: true" in md
    assert "GENERATED FILE" in md
    assert "Modules/M-CORE" in md


def test_canvas_valid_json_and_refs(tmp_path: Path):
    cfg = _fixture_config(tmp_path)
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    canvases = build_all_canvases(graph, report)
    required = [
        "Canvas/Project-Overview.canvas",
        "Canvas/Current-Phase.canvas",
        "Canvas/User-Journey.canvas",
        "Canvas/Requirement-Traceability.canvas",
        "Canvas/Verification-Gaps.canvas",
    ]
    for rel in required:
        assert rel in canvases
    note_paths = {note_relpath(n).replace("\\", "/") for n in graph.nodes.values()}
    for rel, text in canvases.items():
        data = json.loads(text)
        assert "nodes" in data and "edges" in data
        data2 = json.loads(dumps_canvas(data))
        assert data2 == data
        missing = validate_canvas_file_refs(data, note_paths)
        assert missing == [], f"{rel} missing {missing}"


def test_export_vault_and_determinism(tmp_path: Path):
    cfg = _fixture_config(tmp_path)
    graph, _ = build_graph(cfg, include_source=True)
    r1 = export_vault(graph, cfg, clean=True, generated_at="2020-01-01T00:00:00Z")
    vault = Path(r1["vault"])
    assert (vault / "Home.md").is_file()
    assert (vault / ".grace-atlas-generated").is_file()
    assert (vault / "Modules" / "M-CORE.md").is_file()
    assert (vault / "Canvas" / "Project-Overview.canvas").is_file()
    assert (vault / "Diagnostics" / "Summary.md").is_file()
    home = (vault / "Home.md").read_text(encoding="utf-8")
    # Home must not star-link every module
    assert home.count("[[Modules/") < 5
    assert "Canvas/Project-Overview" in home
    # wiki links present in module notes
    core = (vault / "Modules" / "M-CORE.md").read_text(encoding="utf-8")
    assert "[[" in core

    g1 = (vault / "_atlas" / "graph.json").read_text(encoding="utf-8")
    r2 = export_vault(graph, cfg, clean=True, generated_at="2020-01-01T00:00:00Z")
    g2 = (Path(r2["vault"]) / "_atlas" / "graph.json").read_text(encoding="utf-8")
    assert g1 == g2


def test_vault_safety_refuses_repo_root():
    cfg = _fixture_config()
    with pytest.raises(VaultSafetyError):
        assert_safe_vault_path(cfg.repo_root, cfg.repo_root)


def test_is_atlas_vault_marker(tmp_path: Path):
    d = tmp_path / "v"
    d.mkdir()
    assert is_atlas_vault(d)  # empty ok
    (d / "noise.txt").write_text("x", encoding="utf-8")
    assert not is_atlas_vault(d)
    (d / ".grace-atlas-generated").write_text("{}", encoding="utf-8")
    assert is_atlas_vault(d)


def test_trace_tree():
    cfg = _fixture_config()
    graph, _ = build_graph(cfg, include_source=False)
    out = format_trace(graph, "M-CORE")
    assert "M-CORE" in out
    assert "implemented_in" in out or "verified_by" in out

# FILE: tools/grace_atlas/tests/test_parsers_and_export.py
# VERSION: 0.2.0

from __future__ import annotations

import json
from pathlib import Path

from grace_atlas.config import load_config
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.exporters.obsidian import export_vault
from grace_atlas.graph import build_graph
from grace_atlas.model import NodeType
from grace_atlas.source_links import vscode_uri


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_build_graph_from_real_artifacts():
    root = _repo_root()
    cfg = load_config(repo_root=root)
    graph, arts = build_graph(cfg, include_source=False)
    assert arts.knowledge_graph is not None
    assert len(graph.nodes_by_type(NodeType.MODULE)) >= 50
    assert len(graph.nodes_by_type(NodeType.USE_CASE)) >= 10
    assert len(graph.nodes_by_type(NodeType.VERIFICATION)) >= 20
    assert graph.get("M-MODELS") is not None
    assert graph.get("UC-001") is not None


def test_export_real_repo_smoke(tmp_path: Path):
    root = _repo_root()
    cfg = load_config(repo_root=root)
    cfg.vault_path = tmp_path / "vault"
    graph, _ = build_graph(cfg, include_source=False)
    result = export_vault(graph, cfg, clean=True, generated_at="2020-01-01T00:00:00Z")
    vault = Path(result["vault"])
    assert (vault / "Home.md").is_file()
    assert (vault / "Modules" / "M-MODELS.md").is_file()
    assert (vault / "Canvas" / "User-Journey.canvas").is_file()
    assert (vault / "Diagnostics" / "Broken-References.md").is_file()
    md = (vault / "Modules" / "M-MODELS.md").read_text(encoding="utf-8")
    assert "[[" in md
    assert "generated: true" in md
    data = json.loads((vault / "Canvas" / "Project-Overview.canvas").read_text(encoding="utf-8"))
    assert "nodes" in data


def test_gap_report_runs():
    root = _repo_root()
    cfg = load_config(repo_root=root)
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    assert report.summary["modules"] >= 1


def test_vscode_uri_contains_file():
    uri = vscode_uri(Path("C:/tmp/foo.py"), line=10)
    assert uri.startswith("vscode://file")
    assert "foo.py" in uri
    assert uri.endswith(":10")

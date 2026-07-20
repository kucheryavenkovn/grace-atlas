# FILE: tools/grace_atlas/tests/test_workbench.py
# VERSION: 0.3.0
# PURPOSE: Phase 2 workbench — properties, bases, dashboards, enrichment.

from __future__ import annotations

from pathlib import Path

from grace_atlas.config import load_config
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.enrichment import enrich_graph
from grace_atlas.exporters.bases import all_bases, requirements_base
from grace_atlas.exporters.markdown import render_frontmatter, render_node_note
from grace_atlas.exporters.obsidian import export_vault
from grace_atlas.exporters.workbench import render_workbench_pages
from grace_atlas.graph import build_graph
from grace_atlas.model import NodeType

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal"


def _cfg(tmp_path: Path | None = None):
    cfg = load_config(repo_root=FIXTURE, config_path=FIXTURE / "grace-atlas.toml")
    if tmp_path is not None:
        cfg.vault_path = tmp_path / "vault"
    return cfg


def test_enrichment_sets_requirement_type_and_gaps():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    uc = graph.get("UC-001")
    assert uc is not None
    assert uc.properties.get("requirement_type") == "use_case"
    assert uc.properties.get("grace_type") == "use_case"
    assert "has_traceability_gap" in uc.properties
    mod = graph.get("M-UNVERIFIED")
    assert mod is not None
    assert mod.properties.get("has_traceability_gap") is True


def test_frontmatter_unified_schema():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    enrich_graph(graph, build_gap_report(graph))
    uc = graph.get("UC-001")
    fm = render_frontmatter(uc)
    assert "grace_id:" in fm
    assert "grace_type:" in fm
    assert "display_name:" in fm
    assert "generated: true" in fm
    assert "requirement_type:" in fm


def test_human_card_has_sections():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    enrich_graph(graph, build_gap_report(graph))
    mod = graph.get("M-CORE")
    md = render_node_note(mod, graph, cfg)
    assert "Формулировка" in md
    assert "Классификация" in md
    assert "Проблемы" in md or "Трассировка" in md
    assert "[[" in md
    assert "generated: true" in md


def test_bases_yaml_valid_structure():
    bases = all_bases()
    assert "Views/Requirements.base" in bases
    assert "Views/Modules.base" in bases
    assert "Views/Gaps.base" in bases
    rb = requirements_base()
    assert "views:" in rb
    assert "Все требования" in rb
    assert "Пользовательские сценарии" in rb
    # Columns must use note.<prop> so Bases can read frontmatter
    assert "note.grace_id" in rb
    assert "note.display_name" in rb
    assert "displayName:" in rb
    # Empty map must not break YAML (key + {} on next line)
    assert ":\n{}" not in rb and ":\r\n{}" not in rb
    assert "\t" not in rb


def test_workbench_pages():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    pages = render_workbench_pages(graph, report)
    assert "Dashboards/Workbench.md" in pages
    assert "Dashboards/Requirement-Tree.md" in pages
    assert "Dashboards/Traceability-Matrix.md" in pages
    assert "UC-001" in pages["Dashboards/Requirement-Tree.md"] or "[[" in pages["Dashboards/Requirement-Tree.md"]


def test_export_includes_workbench(tmp_path: Path):
    cfg = _cfg(tmp_path)
    graph, _ = build_graph(cfg, include_source=False)
    result = export_vault(graph, cfg, clean=True, generated_at="2020-01-01T00:00:00Z")
    vault = Path(result["vault"])
    assert (vault / "Dashboards" / "Workbench.md").is_file()
    assert (vault / "Views" / "Requirements.base").is_file()
    assert (vault / "Views" / "Modules.base").is_file()
    assert (vault / "Use-Cases" / "UC-001.md").is_file()
    card = (vault / "Use-Cases" / "UC-001.md").read_text(encoding="utf-8")
    assert "grace_type:" in card
    assert "requirement_type:" in card
    assert "[[Dashboards/Workbench]]" in card or "Local Graph" in card

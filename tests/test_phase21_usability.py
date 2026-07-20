# FILE: tools/grace_atlas/tests/test_phase21_usability.py
# VERSION: 0.3.1
# PURPOSE: Phase 2.1 usability — show card, bases validate, coverage, triage filters.

from __future__ import annotations

from pathlib import Path

from grace_atlas.bases_validate import validate_base_text, validate_bases_dir
from grace_atlas.config import load_config
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.enrichment import enrich_graph
from grace_atlas.exporters.bases import all_bases
from grace_atlas.exporters.obsidian import export_vault
from grace_atlas.exporters.workbench import compute_traceability_coverage, render_workbench_pages
from grace_atlas.findings import filter_triaged, group_by_code, triage_findings
from grace_atlas.graph import build_graph
from grace_atlas.show_card import build_card_data, format_card
from grace_atlas.exporters.notes import note_relpath

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal"


def _cfg(tmp=None):
    cfg = load_config(repo_root=FIXTURE, config_path=FIXTURE / "grace-atlas.toml")
    if tmp is not None:
        cfg.vault_path = tmp / "vault"
    return cfg


def test_base_references_existing_properties():
    for path, text in all_bases().items():
        issues = validate_base_text(path, text)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors, errors


def test_base_views_unique_names():
    for path, text in all_bases().items():
        names = []
        for line in text.splitlines():
            if line.strip().startswith("name:"):
                names.append(line.split(":", 1)[1].strip().strip('"'))
        assert len(names) == len(set(names)), f"dup in {path}: {names}"


def test_show_human_card():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    enrich_graph(graph, build_gap_report(graph))
    node = graph.get("UC-001")
    assert node
    data = build_card_data(graph, node, "Use-Cases/UC-001.md")
    human = format_card(data, fmt="human")
    assert "UC-001" in human
    assert "description:" in human or "name:" in human
    assert "gaps:" in human
    assert "note:" in human
    js = format_card(data, fmt="json")
    assert '"id": "UC-001"' in js
    tbl = format_card(data, fmt="table")
    assert "obsidian_note" in tbl


def test_traceability_rows_deduplicated():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    cov = compute_traceability_coverage(graph)
    ids = [r["id"] for r in cov["rows"]]
    assert len(ids) == len(set(ids))
    assert cov["total_use_cases"] == len(ids)
    assert "complete_chains" in cov
    assert cov["complete_chains"] + cov["partial_chains"] + cov["broken_chains"] >= 0


def test_behavior_tree_explains_absent_hierarchy():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    pages = render_workbench_pages(graph, report)
    tree = pages["Dashboards/Requirement-Tree.md"]
    assert "BR:" in tree and "UC:" in tree
    # fixture has only UC — should mention absence of full hierarchy or show zeros
    assert "BR: **0**" in tree or "не содержат" in tree
    assert "Dashboards/Behavior-Tree.md" in pages
    assert "не" in pages["Dashboards/Behavior-Tree.md"] or "UC" in pages["Dashboards/Behavior-Tree.md"]


def test_findings_group_and_filter():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    triaged = triage_findings(graph, report)
    assert triaged
    groups = group_by_code(triaged)
    assert groups
    assert all("code" in g and "count" in g for g in groups)
    actionable = filter_triaged(triaged, actionable=True)
    assert all(f.suppression_eligibility == "actionable" for f in actionable)
    # suppressed stay auditable when include_suppressed
    with_sup = triage_findings(graph, report, suppress=[triaged[0].code])
    assert any(f.suppressed for f in with_sup)
    visible = filter_triaged(with_sup, include_suppressed=False)
    assert all(not f.suppressed for f in visible)
    all_inc = filter_triaged(with_sup, include_suppressed=True)
    assert len(all_inc) >= len(visible)


def test_gap_triage_dashboard_deterministic():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    report = build_gap_report(graph)
    p1 = render_workbench_pages(graph, report)
    p2 = render_workbench_pages(graph, report)
    assert p1["Dashboards/Gap-Triage.md"] == p2["Dashboards/Gap-Triage.md"]
    assert "Summary by code" in p1["Dashboards/Gap-Triage.md"]
    assert "Top 5 actionable" in p1["Dashboards/Gap-Triage.md"]


def test_manual_checklist_generated():
    cfg = _cfg()
    graph, _ = build_graph(cfg, include_source=False)
    pages = render_workbench_pages(graph, build_gap_report(graph))
    cl = pages["Dashboards/Manual-Acceptance-Checklist.md"]
    assert "- [ ]" in cl
    assert "Local Graph" in cl
    assert "UC-001" in cl


def test_export_has_phase21_dashboards(tmp_path: Path):
    cfg = _cfg(tmp_path)
    graph, _ = build_graph(cfg, include_source=False)
    export_vault(graph, cfg, clean=True, generated_at="2020-01-01T00:00:00Z")
    vault = cfg.resolve_vault()
    assert (vault / "Dashboards" / "Gap-Triage.md").is_file()
    assert (vault / "Dashboards" / "Traceability-Coverage.md").is_file()
    assert (vault / "Dashboards" / "Manual-Acceptance-Checklist.md").is_file()
    assert (vault / "Dashboards" / "Behavior-Tree.md").is_file()
    vr = validate_bases_dir(vault / "Views")
    assert vr.bases_checked
    # no hard errors preferred
    hard = [i for i in vr.issues if i.severity == "error"]
    assert not hard, hard

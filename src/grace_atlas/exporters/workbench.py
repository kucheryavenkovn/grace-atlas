# FILE: tools/grace_atlas/src/grace_atlas/exporters/workbench.py
# VERSION: 0.3.1
# PURPOSE: Human dashboards — tree, matrix, coverage, journey, gap triage, checklists.

"""Workbench markdown dashboards (read-only projection)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from grace_atlas.bases_validate import BaseValidationReport, render_validation_markdown, validate_bases_dir
from grace_atlas.diagnostics import GapReport
from grace_atlas.exporters.markdown import GENERATED_BANNER
from grace_atlas.exporters.notes import wikilink
from grace_atlas.findings import (
    USER_JOURNEY_IDS,
    TriagedFinding,
    filter_triaged,
    group_by_code,
    top_actionable,
    triage_findings,
)
from grace_atlas.model import AtlasGraph, EdgeType, NodeType


def render_workbench_pages(
    graph: AtlasGraph,
    report: GapReport,
    *,
    triaged: list[TriagedFinding] | None = None,
    bases_report: BaseValidationReport | None = None,
) -> dict[str, str]:
    if triaged is None:
        triaged = triage_findings(graph, report)
    coverage = compute_traceability_coverage(graph)
    pages: dict[str, str] = {}
    pages["Dashboards/Workbench.md"] = _workbench_home(graph, report, triaged, coverage)
    pages["Dashboards/Requirement-Tree.md"] = _requirement_tree(graph)
    pages["Dashboards/Behavior-Tree.md"] = _behavior_tree(graph)
    pages["Dashboards/Traceability-Matrix.md"] = _traceability_matrix(graph, coverage)
    pages["Dashboards/Traceability-Coverage.md"] = _coverage_page(coverage)
    pages["Dashboards/User-Journey-Video2PPTX.md"] = _user_journey(graph)
    pages["Dashboards/Gap-Triage.md"] = _gap_triage(graph, triaged)
    pages["Dashboards/Manual-Acceptance-Checklist.md"] = _manual_checklist()
    pages["Dashboards/How-to-use.md"] = _howto()
    pages["Dashboards/Round-Trip-Status.md"] = _roundtrip_stub()
    pages["Dashboards/Phase-3A-Manual-Acceptance.md"] = _phase3a_checklist()
    pages["Diagnostics/Gaps-Registry.md"] = _gaps_registry(graph, report, triaged)
    if bases_report is not None:
        pages["Dashboards/Bases-Validation.md"] = render_validation_markdown(bases_report)
    return pages


def _header(title: str) -> list[str]:
    return [
        GENERATED_BANNER,
        "",
        "---",
        "generated: true",
        "tags: [grace-atlas, grace/workbench, grace/index]",
        "---",
        "",
        f"# {title}",
        "",
        "> Сгенерировано GRACE Atlas. Ручные правки будут потеряны при rebuild.",
        "",
    ]


def compute_traceability_coverage(graph: AtlasGraph) -> dict[str, Any]:
    ucs = sorted(graph.nodes_by_type(NodeType.USE_CASE), key=lambda n: n.id)
    # Dedup rows by UC id
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for uc in ucs:
        if uc.id in seen:
            continue
        seen.add(uc.id)
        has_flow = any(e.source == uc.id and e.type == EdgeType.RELATED_FLOW for e in graph.edges)
        has_vf = any(e.target == uc.id and e.type == EdgeType.USES_USE_CASE for e in graph.edges)
        # derived: module/file/v/test via VF only marked as derived, not declared UC→module
        has_mod = bool(uc.properties.get("implemented_by") or uc.properties.get("implements"))
        has_file = bool(uc.properties.get("implemented_in"))
        has_v = bool(uc.properties.get("verified_by"))
        has_t = bool(uc.properties.get("tested_by"))
        has_ev = bool(uc.properties.get("evidence"))
        # chain quality
        if has_flow and has_vf and (has_mod or has_v):
            chain = "partial"
        elif has_flow or has_vf:
            chain = "partial"
        else:
            chain = "broken"
        # complete would need full declared UC→module→file→v→test→evidence (rare)
        if has_mod and has_file and has_v and has_t and has_ev:
            chain = "complete"
        elif not (has_flow or has_vf or has_mod):
            chain = "broken"
        rows.append(
            {
                "id": uc.id,
                "name": uc.name,
                "flow": has_flow,
                "vf": has_vf,
                "module": has_mod,
                "file": has_file,
                "verification": has_v,
                "tests": has_t,
                "evidence": has_ev,
                "chain": chain,
                "gaps": list(uc.properties.get("gap_types") or []),
                "source_state": uc.properties.get("source_state") or "declared",
            }
        )

    def count(pred) -> int:
        return sum(1 for r in rows if pred(r))

    return {
        "total_use_cases": len(rows),
        "linked_to_flows": count(lambda r: r["flow"]),
        "linked_to_modules": count(lambda r: r["module"]),
        "linked_to_source_files": count(lambda r: r["file"]),
        "linked_to_verification": count(lambda r: r["verification"] or r["vf"]),
        "linked_to_tests": count(lambda r: r["tests"]),
        "linked_to_evidence": count(lambda r: r["evidence"]),
        "complete_chains": count(lambda r: r["chain"] == "complete"),
        "partial_chains": count(lambda r: r["chain"] == "partial"),
        "broken_chains": count(lambda r: r["chain"] == "broken"),
        "rows": rows,
    }


def _workbench_home(
    graph: AtlasGraph,
    report: GapReport,
    triaged: list[TriagedFinding],
    coverage: dict[str, Any],
) -> str:
    actionable = filter_triaged(triaged, actionable=True)
    lines = _header("GRACE Workbench")
    lines.extend(
        [
            "Главный человеческий вход. **Не** используйте глобальный Graph View как основной UI.",
            "",
            "## 1. Реестры (Obsidian Bases)",
            "",
            "- [[Views/Requirements.base|Требования]]",
            "- [[Views/Modules.base|Модули]]",
            "- [[Views/Verification.base|Верификация]]",
            "- [[Views/Current-Work.base|Текущая работа]]",
            "- [[Views/Gaps.base|Gaps]]",
            "- [[Views/Source-Files.base|Исходные файлы]]",
            "- [[Dashboards/Bases-Validation|Проверка Bases]]",
            "",
            "## 2. Деревья и матрицы",
            "",
            "- [[Dashboards/Requirement-Tree|Дерево требований / UC]]",
            "- [[Dashboards/Behavior-Tree|Behavior tree (честная иерархия)]]",
            "- [[Dashboards/Traceability-Matrix|Матрица трассируемости]]",
            "- [[Dashboards/Traceability-Coverage|Покрытие трассируемости]]",
            "- [[Dashboards/User-Journey-Video2PPTX|Пользовательский сценарий]]",
            "- [[Dashboards/Gap-Triage|Триаж gaps]]",
            "- [[Dashboards/Manual-Acceptance-Checklist|Ручная приёмка]]",
            "",
            "## 3. Сводка",
            "",
            f"- Узлы: **{len(graph.nodes)}** · Рёбра: **{len(graph.edges)}**",
            f"- Findings: **{len(triaged)}** · actionable: **{len(actionable)}**",
            f"- UC всего: **{coverage['total_use_cases']}** · "
            f"частичные цепочки: **{coverage['partial_chains']}** · "
            f"разорванные: **{coverage['broken_chains']}** · "
            f"полные: **{coverage['complete_chains']}**",
            "",
            "## 4. Как работать",
            "",
            "См. [[Dashboards/How-to-use]] и [[Dashboards/Manual-Acceptance-Checklist]].",
            "",
        ]
    )
    return "\n".join(lines)


def _hierarchy_counts(graph: AtlasGraph) -> dict[str, int]:
    def count_prefix(prefix: str) -> int:
        return sum(1 for n in graph.nodes.values() if n.id.startswith(prefix))

    return {
        "BR": count_prefix("BR-"),
        "UR": count_prefix("UR-"),
        "FR": count_prefix("FR-"),
        "NFR": count_prefix("NFR-"),
        "AC": count_prefix("AC-"),
        "UC": len(graph.nodes_by_type(NodeType.USE_CASE)),
        "constraints": len(graph.nodes_by_type(NodeType.CONSTRAINT)),
        "risks": len(graph.nodes_by_type(NodeType.RISK)),
    }


def _requirement_tree(graph: AtlasGraph) -> str:
    counts = _hierarchy_counts(graph)
    lines = _header("Дерево требований")
    lines.extend(
        [
            "## Иерархия в исходных данных",
            "",
            f"- BR: **{counts['BR']}** · UR: **{counts['UR']}** · FR: **{counts['FR']}** · "
            f"NFR: **{counts['NFR']}** · AC: **{counts['AC']}**",
            f"- UC: **{counts['UC']}** · constraints: **{counts['constraints']}** · "
            f"risks: **{counts['risks']}**",
            "",
        ]
    )
    if counts["BR"] + counts["UR"] + counts["FR"] + counts["NFR"] + counts["AC"] == 0:
        lines.extend(
            [
                "> **Важно:** исходные GRACE-артефакты Video2PPTX **не содержат** полноценной иерархии "
                "BR → UR → FR → AC. Ниже показано доступное дерево "
                "**Use Case → Flow → Verification Flow** (declared связи).",
                "",
                "См. также [[Dashboards/Behavior-Tree]].",
                "",
            ]
        )
    lines.append("## Use cases")
    lines.append("")
    for uc in sorted(graph.nodes_by_type(NodeType.USE_CASE), key=lambda n: n.id):
        gap = " ⚠" if uc.properties.get("has_traceability_gap") else ""
        lines.append(f"- {wikilink(uc, uc.id)} — {uc.name or ''}{gap}")
        for e in graph.edges:
            if e.source == uc.id and e.type == EdgeType.RELATED_FLOW:
                tgt = graph.get(e.target)
                if tgt:
                    lines.append(f"  - flow *(declared)*: {wikilink(tgt, tgt.id)}")
        for e in graph.edges:
            if e.target == uc.id and e.type == EdgeType.USES_USE_CASE:
                src = graph.get(e.source)
                if src:
                    lines.append(f"  - VF *(declared)*: {wikilink(src, src.id)}")
        lines.append("")
    return "\n".join(lines)


def _behavior_tree(graph: AtlasGraph) -> str:
    counts = _hierarchy_counts(graph)
    lines = _header("Behavior tree (Use Case → Flow → VF)")
    lines.extend(
        [
            "Это **не** hierarchy BR/UR/FR. Это behavioral map declared use cases.",
            "",
            f"Taxonomy counts: BR={counts['BR']} UR={counts['UR']} FR={counts['FR']} "
            f"NFR={counts['NFR']} AC={counts['AC']} UC={counts['UC']}",
            "",
        ]
    )
    for uc in sorted(graph.nodes_by_type(NodeType.USE_CASE), key=lambda n: n.id):
        lines.append(f"### {wikilink(uc, uc.id)}")
        lines.append("")
        lines.append(f"{uc.name}")
        lines.append("")
        flows = [e.target for e in graph.edges if e.source == uc.id and e.type == EdgeType.RELATED_FLOW]
        vfs = [e.source for e in graph.edges if e.target == uc.id and e.type == EdgeType.USES_USE_CASE]
        if flows:
            lines.append("Flows:")
            for fid in flows:
                n = graph.get(fid)
                lines.append(f"- {wikilink(n, fid) if n else fid}")
        else:
            lines.append("- flows: _none declared_")
        if vfs:
            lines.append("Verification flows:")
            for vid in vfs:
                n = graph.get(vid)
                lines.append(f"- {wikilink(n, vid) if n else vid}")
        else:
            lines.append("- VF: _none declared_")
        lines.append("")
    return "\n".join(lines)


def _traceability_matrix(graph: AtlasGraph, coverage: dict[str, Any]) -> str:
    lines = _header("Матрица трассировки")
    lines.extend(
        [
            "Одна строка на Use Case (deduplicated). "
            "✓ = declared link present. Module/file/V/test often **absent** as direct UC edges "
            "(go via VF) — marked only when properties show declared links.",
            "",
            f"Coverage summary: complete={coverage['complete_chains']} "
            f"partial={coverage['partial_chains']} broken={coverage['broken_chains']} "
            f"(of {coverage['total_use_cases']} UC). "
            "Details: [[Dashboards/Traceability-Coverage]].",
            "",
            "| ID | Name | Flow | VF | Module | File | V-M | Test | Evidence | Chain | Gaps |",
            "|----|------|------|----|--------|------|-----|------|----------|-------|------|",
        ]
    )
    for r in coverage["rows"]:
        n = graph.get(r["id"])
        link = wikilink(n, r["id"]) if n else r["id"]
        def m(b: bool) -> str:
            return "✓" if b else "—"

        gaps = ",".join(r["gaps"][:2]) or "—"
        lines.append(
            f"| {link} | {(r['name'] or '')[:40]} | {m(r['flow'])} | {m(r['vf'])} | "
            f"{m(r['module'])} | {m(r['file'])} | {m(r['verification'])} | {m(r['tests'])} | "
            f"{m(r['evidence'])} | `{r['chain']}` | {gaps} |"
        )
    lines.append("")
    lines.extend(
        [
            "### Legend",
            "",
            "- **declared**: edge/property from GRACE XML",
            "- **chain=partial**: has flow and/or VF but incomplete product chain",
            "- **chain=broken**: no flow/VF/module links",
            "- **chain=complete**: module+file+V+test+evidence (rare without explicit UC→module)",
            "",
        ]
    )
    return "\n".join(lines)


def _coverage_page(coverage: dict[str, Any]) -> str:
    lines = _header("Traceability coverage")
    lines.extend(
        [
            "| Metric | Count |",
            "|--------|------:|",
            f"| total use cases | {coverage['total_use_cases']} |",
            f"| use cases linked to flows | {coverage['linked_to_flows']} |",
            f"| use cases linked to modules (direct) | {coverage['linked_to_modules']} |",
            f"| use cases linked to source files (direct) | {coverage['linked_to_source_files']} |",
            f"| use cases linked to verification (V or VF) | {coverage['linked_to_verification']} |",
            f"| use cases linked to tests (direct) | {coverage['linked_to_tests']} |",
            f"| use cases linked to evidence (direct) | {coverage['linked_to_evidence']} |",
            f"| complete traceability chains | {coverage['complete_chains']} |",
            f"| partial chains | {coverage['partial_chains']} |",
            f"| broken chains | {coverage['broken_chains']} |",
            "",
            "Matrix: [[Dashboards/Traceability-Matrix]].",
            "",
        ]
    )
    return "\n".join(lines)


JOURNEY_STAGES = [
    ("Installation on clean Windows", [], "Often product packaging — may lack UC"),
    ("Launch without Python", [], "Packaging / GUI bootstrap"),
    ("Create project", ["UC-008"], ""),
    ("Load video", ["UC-008", "UC-013"], ""),
    ("Load subtitles", ["UC-006", "UC-013"], ""),
    ("Auto", ["UC-009"], "May map via detect-in-project"),
    ("Detect", ["UC-001", "UC-005", "UC-009"], ""),
    ("PPTX generation", ["UC-002"], ""),
    ("Save", ["UC-008", "UC-013"], ""),
    ("Close", ["UC-013"], ""),
    ("Reopen", ["UC-008", "UC-013"], ""),
    ("Persistence validation", ["UC-008"], ""),
]


def _user_journey(graph: AtlasGraph) -> str:
    lines = _header("Базовый пользовательский путь Video2PPTX")
    lines.extend(
        [
            "Только **declared** use cases. Сопоставление по ID, не по «похожим именам».",
            "Phase 18 Detect performance **не** смешивается с acceptance user journey "
            "(см. Phase-18 / perf verification отдельно).",
            "",
            "| Stage | UC | Module* | Verification* | Test* | Evidence* | source_state | Gap |",
            "|-------|----|---------|---------------|-------|-----------|--------------|-----|",
        ]
    )
    for title, uc_ids, note in JOURNEY_STAGES:
        if not uc_ids:
            lines.append(
                f"| {title} | — | — | — | — | — | — | **gap**: no declared UC in GRACE |"
            )
            continue
        found_any = False
        for uid in uc_ids:
            n = graph.get(uid)
            if not n:
                continue
            found_any = True
            has_vf = any(e.target == uid and e.type == EdgeType.USES_USE_CASE for e in graph.edges)
            mod = "—"  # direct declared rare
            if n.properties.get("implements") or n.properties.get("implemented_by"):
                mod = "✓"
            ver = "✓" if has_vf or n.properties.get("verified_by") else "—"
            test = "✓" if n.properties.get("tested_by") else "—"
            ev = "✓" if n.properties.get("evidence") else "—"
            gaps = ",".join((n.properties.get("gap_types") or [])[:2]) or "—"
            link = wikilink(n, uid)
            lines.append(
                f"| {title} | {link} | {mod}* | {ver} | {test}* | {ev}* | "
                f"{n.properties.get('source_state', 'declared')} | {gaps} |"
            )
        if not found_any:
            lines.append(
                f"| {title} | {', '.join(uc_ids)} | — | — | — | — | — | **gap**: UC id missing |"
            )
    lines.extend(
        [
            "",
            "\\* Module/Test/Evidence columns for UC are usually empty as **direct** links — "
            "product wiring often goes UC → VF → Module *(declared VF only marked under Verification)*.",
            "",
            "### Phase 18 performance (separate)",
            "",
            "Do not treat Phase-18 Detect bottleneck work as user-journey acceptance evidence.",
            "See phases: [[Phases/Phase-18]] if present.",
            "",
        ]
    )
    return "\n".join(lines)


def _gap_triage(graph: AtlasGraph, triaged: list[TriagedFinding]) -> str:
    lines = _header("Gap triage")
    lines.extend(
        [
            "Findings enriched for human triage. Suppressed findings remain listed in audit section.",
            "",
        ]
    )
    by_sev = Counter(f.severity for f in triaged if not f.suppressed)
    by_elig = Counter(f.suppression_eligibility for f in triaged)
    lines.append(
        f"Total: **{len(triaged)}** · error={by_sev.get('error', 0)} "
        f"warning={by_sev.get('warning', 0)} info={by_sev.get('info', 0)} · "
        f"actionable={by_elig.get('actionable', 0)} informational={by_elig.get('informational', 0)} "
        f"expected={by_elig.get('expected', 0)} suppressed={by_elig.get('suppressed', 0)}"
    )
    lines.append("")

    # Summary table by code
    groups = group_by_code([f for f in triaged if not f.suppressed])
    lines.extend(
        [
            "## Summary by code",
            "",
            "| Finding code | Severity | Count | Affected (sample) | Suggested action |",
            "|--------------|----------|------:|-------------------|------------------|",
        ]
    )
    for g in groups[:40]:
        ents = ", ".join(g["affected_entities"][:5])
        if g["affected_count"] > 5:
            ents += f" (+{g['affected_count'] - 5})"
        lines.append(
            f"| `{g['code']}` | {g['severity']} | {g['count']} | {ents or '—'} | {g['suggested_action']} |"
        )
    lines.append("")

    def section(title: str, rows: list[TriagedFinding], limit: int = 25) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not rows:
            lines.append("_Нет записей (это не ошибка)._")
            lines.append("")
            return
        for f in rows[:limit]:
            lines.append(
                f"- **{f.severity}** `{f.code}` `{f.entity_id or '—'}` — {f.message[:120]} "
                f"→ _{f.suggested_action}_"
            )
        if len(rows) > limit:
            lines.append(f"- … and {len(rows) - limit} more")
        lines.append("")

    section("1. Critical errors", [f for f in triaged if f.severity == "error" and not f.suppressed])
    section(
        "2. User journey relevant",
        filter_triaged(triaged, user_journey=True),
    )
    section(
        "3. Current phase relevant",
        filter_triaged(triaged, current_phase=True),
    )
    section(
        "4. Actionable",
        filter_triaged(triaged, actionable=True),
    )
    section(
        "5. Informational",
        [f for f in triaged if f.suppression_eligibility == "informational" and not f.suppressed],
        limit=15,
    )
    section(
        "6. Expected / potentially suppressible",
        [f for f in triaged if f.suppression_eligibility in {"expected", "suppressed"}],
        limit=15,
    )

    top = top_actionable(triaged, 5)
    lines.append("## Top 5 actionable")
    lines.append("")
    for i, f in enumerate(top, 1):
        lines.append(f"{i}. `{f.code}` on `{f.entity_id}` — {f.suggested_action}")
    lines.append("")
    return "\n".join(lines)


def _gaps_registry(graph: AtlasGraph, report: GapReport, triaged: list[TriagedFinding]) -> str:
    lines = _header("Реестр gaps")
    lines.append("См. triage: [[Dashboards/Gap-Triage]].")
    lines.append("")
    lines.append(f"Raw findings: **{len(report.findings)}** · triaged: **{len(triaged)}**")
    lines.append("")
    lines.append("| Severity | Code | Entity | Category | Eligibility | Message |")
    lines.append("|----------|------|--------|----------|-------------|---------|")
    for f in sorted(triaged, key=lambda x: (x.severity, x.code, x.entity_id))[:200]:
        msg = f.message.replace("|", "/")[:80]
        lines.append(
            f"| {f.severity} | `{f.code}` | `{f.entity_id or '—'}` | {f.category} | "
            f"{f.suppression_eligibility} | {msg} |"
        )
    lines.append("")
    return "\n".join(lines)


def _manual_checklist() -> str:
    steps = [
        ("Build Vault", "`python tools/grace_atlas.py build --project-root .`", "Vault under `.grace-atlas/vault`"),
        ("Open Vault in Obsidian", "Open folder as vault → `.grace-atlas/vault`", "Home / Workbench visible"),
        ("Open Workbench", "Open `Dashboards/Workbench.md`", "Links to Bases and dashboards"),
        ("Open Requirements.base", "Open `Views/Requirements.base`", "Table loads without YAML error"),
        ("Filter use_case", "Switch view «Пользовательские сценарии»", "UC rows visible; columns filled"),
        ("Open UC-001", "Click UC-001 row / open `Use-Cases/UC-001.md`", "Human card with properties"),
        ("Local Graph depth 1", "Ctrl+P → Open local graph, depth=1", "Neighbors of UC-001"),
        ("Local Graph depth 2", "Set depth=2", "Expanded neighborhood"),
        ("Navigate to flow", "Click DF/related flow link", "Flow note opens"),
        ("Navigate to module", "From VF or Modules index to a module", "Module card opens"),
        ("Navigate to source file", "From module implemented_in", "Source-Files note"),
        ("Open in VS Code", "Click vscode:// link", "Editor opens file"),
        ("Return to UC", "Back / search UC-001", "Card again"),
        ("Traceability Matrix", "Open `Dashboards/Traceability-Matrix.md`", "One row per UC"),
        ("Gap Triage", "Open `Dashboards/Gap-Triage.md`", "Grouped findings + top 5"),
        ("Five highest-priority gaps", "From Gap Triage top actionable", "List five concrete gaps"),
    ]
    lines = _header("Manual Acceptance Checklist")
    lines.extend(
        [
            "Ручная проверка Human Workbench. Автоматизация Obsidian UI **недоступна** в CI.",
            "",
        ]
    )
    for i, (title, action, expected) in enumerate(steps, 1):
        lines.append(f"### {i}. {title}")
        lines.append("")
        lines.append(f"- [ ] **Action:** {action}")
        lines.append(f"- [ ] **Expected:** {expected}")
        lines.append(f"- [ ] **Result:** _pass / fail_ — notes: ________")
        lines.append("")
    return "\n".join(lines)


def _howto() -> str:
    lines = _header("Как пользоваться workbench")
    lines.extend(
        [
            "1. [[Dashboards/Workbench]] → Bases / dashboards.",
            "2. Карточка сущности → Local Graph (depth 1–2).",
            "3. CLI: `python -m grace_atlas show UC-001 --project-root .`",
            "4. Gaps: `python -m grace_atlas gaps --actionable --project-root .`",
            "5. Checklist: [[Dashboards/Manual-Acceptance-Checklist]].",
            "6. Плагин Workbench Phase 3: команда **GRACE: Открыть Workbench**.",
            "7. Snapshot: `python -m grace_atlas snapshot build --project-root .`",
            "8. Round-trip: [[Dashboards/Round-Trip-Status]].",
            "",
            "Declared vs inferred: inferred помечается в теле; gaps никогда не «чинятся» автоматически.",
            "",
        ]
    )
    return "\n".join(lines)


def _roundtrip_stub() -> str:
    lines = _header("Статус Round-Trip")
    lines.extend(
        [
            "Контроль соответствия: модель GRACE ↔ source markup ↔ файлы ↔ тесты ↔ evidence.",
            "",
            "**Важно:** inferred-предложения **никогда** не становятся declared без GracePatch и подтверждения.",
            "",
            "## CLI",
            "",
            "```bash",
            "python -m grace_atlas scan --project-root .",
            "python -m grace_atlas drift --project-root . --json",
            "python -m grace_atlas impact M-APP-AUTO --project-root .",
            "python -m grace_atlas snapshot build --project-root .",
            "```",
            "",
            "Полный live-отчёт (после scan):",
            "",
            "```bash",
            "python -c \"from pathlib import Path; from grace_atlas.config import load_config; "
            "from grace_atlas.roundtrip.dashboard import write_roundtrip_dashboard; "
            "print(write_roundtrip_dashboard(load_config(repo_root=Path('.'))))\"",
            "```",
            "",
            "См. также панели Round-trip в плагине (Phase 3D) и `.grace-atlas/user/fingerprints.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def _phase3a_checklist() -> str:
    lines = _header("Phase 3A — ручная приёмка")
    lines.extend(
        [
            "Исходный checklist: `tools/grace_atlas/docs/Phase-3A-Manual-Acceptance.md`.",
            "",
            "- [ ] Открыть Workbench",
            "- [ ] UC-001: выбор + диаграмма + инспектор",
            "- [ ] Окрестность M-APP-AUTO",
            "- [ ] Назад / Вперёд",
            "- [ ] XML GRACE не изменён",
            "",
        ]
    )
    return "\n".join(lines)

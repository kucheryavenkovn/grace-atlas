# FILE: tools/grace_atlas/src/grace_atlas/diagnostics.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Traceability gap diagnostics with multi-file Markdown reports.
#   SCOPE: broken refs, orphans, unverified modules, unmapped files, ambiguous links
#   DEPENDS: grace_atlas.model
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Traceability gap diagnostics (declared vs inferred vs unresolved)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grace_atlas.model import AtlasGraph, EdgeType, Node, NodeType, Provenance


@dataclass
class GapFinding:
    code: str
    severity: str  # error | warning | info
    message: str
    entity_id: str = ""
    provenance: str = "declared"  # declared | inferred | unresolved
    source_path: str = ""
    source_line: int | None = None
    related: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GapReport:
    findings: list[GapFinding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def add(
        self,
        code: str,
        severity: str,
        message: str,
        entity_id: str = "",
        *,
        provenance: str = "declared",
        source_path: str = "",
        source_line: int | None = None,
        related: list[str] | None = None,
        **details: Any,
    ) -> None:
        self.findings.append(
            GapFinding(
                code=code,
                severity=severity,
                message=message,
                entity_id=entity_id,
                provenance=provenance,
                source_path=source_path,
                source_line=source_line,
                related=list(related or []),
                details=details,
            )
        )

    def by_code(self, code: str) -> list[GapFinding]:
        return [f for f in self.findings if f.code == code]


def build_gap_report(graph: AtlasGraph) -> GapReport:
    report = GapReport()
    modules = graph.nodes_by_type(NodeType.MODULE)
    verifications = graph.nodes_by_type(NodeType.VERIFICATION)
    use_cases = graph.nodes_by_type(NodeType.USE_CASE)
    requirements = graph.nodes_by_type(NodeType.REQUIREMENT)
    files = [n for n in graph.nodes.values() if n.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}]

    verified: set[str] = set()
    implemented: set[str] = set()
    for e in graph.edges:
        if e.type == EdgeType.VERIFIED_BY:
            verified.add(e.source)
        elif e.type == EdgeType.IMPLEMENTED_IN:
            implemented.add(e.source)

    # --- Stub / broken targets ---
    stub_modules = [m for m in modules if m.properties.get("stub")]
    for m in stub_modules:
        report.add(
            "STUB_MODULE",
            "warning",
            f"Module {m.id} is referenced but never fully defined in plan/graph",
            m.id,
            provenance="unresolved",
            source_path=(m.source_ref.path if m.source_ref else ""),
            source_line=m.source_ref.line_start if m.source_ref else None,
            reason="Referenced only as a dependency/verification target",
        )

    # Edge endpoints missing nodes (should be rare — parsers create stubs)
    for e in graph.edges:
        for end in (e.source, e.target):
            if end not in graph.nodes:
                report.add(
                    "BROKEN_REFERENCE",
                    "error",
                    f"Edge {e.type} references missing node {end}",
                    end,
                    provenance="unresolved",
                    source_path=e.artifact_path,
                    related=[e.source, e.target],
                    edge_type=e.type,
                )

    # Missing files on disk
    missing_files = [f for f in files if f.properties.get("missing") or f.properties.get("exists") is False]
    for f in missing_files:
        report.add(
            "MISSING_FILE",
            "error",
            f"Declared path does not exist: {f.properties.get('path') or f.name}",
            f.id,
            provenance="declared",
            source_path=str(f.properties.get("path") or ""),
            related=[e.source for e in graph.edges if e.target == f.id][:10],
            reason="Path declared in GRACE but absent on disk",
        )
        report.add(
            "BROKEN_REFERENCE",
            "error",
            f"Broken file reference: {f.properties.get('path') or f.name}",
            f.id,
            provenance="declared",
            source_path=str(f.properties.get("path") or ""),
        )

    # Modules without verification / source
    unverified = 0
    for m in modules:
        if m.properties.get("stub"):
            continue
        src = m.source_ref.path if m.source_ref else m.source
        if m.id not in verified:
            unverified += 1
            report.add(
                "UNVERIFIED_MODULE",
                "warning",
                f"Module {m.id} has no verified_by edge",
                m.id,
                provenance="declared",
                source_path=src or "",
                source_line=m.source_ref.line_start if m.source_ref else None,
                status=m.status,
                reason="No V-M-* link from knowledge-graph/plan/verification",
            )
        if m.id not in implemented:
            status = (m.status or "").lower()
            sev = "info" if status in {"planned", "pending"} else "warning"
            report.add(
                "MODULE_WITHOUT_SOURCE",
                sev,
                f"Module {m.id} has no implemented_in path link",
                m.id,
                provenance="declared",
                source_path=src or "",
                status=m.status,
            )

    # Verification without tests
    for v in verifications:
        if v.properties.get("stub"):
            report.add(
                "STUB_VERIFICATION",
                "info",
                f"Verification {v.id} referenced but not fully defined",
                v.id,
                provenance="unresolved",
            )
            continue
        tests = v.properties.get("test_files") or []
        status = (v.status or "").lower()
        if not tests and status not in {"blocked", "planned", "pending"}:
            report.add(
                "VERIFICATION_WITHOUT_TESTS",
                "warning",
                f"Verification {v.id} has no test-files (status={v.status})",
                v.id,
                provenance="declared",
                source_path=v.source_ref.path if v.source_ref else "",
                status=v.status,
            )
        if status == "blocked":
            report.add(
                "VERIFICATION_BLOCKED",
                "info",
                f"Verification {v.id} is blocked: {v.properties.get('blocked_reason') or ''}",
                v.id,
                provenance="declared",
            )

    # Orphan use cases / requirements (no outgoing related edges)
    linked_uc: set[str] = set()
    for e in graph.edges:
        if e.type in {EdgeType.RELATED_FLOW, EdgeType.USES_USE_CASE, EdgeType.IMPLEMENTS}:
            linked_uc.add(e.source)
            linked_uc.add(e.target)
    for uc in use_cases:
        if uc.id not in linked_uc and not uc.properties.get("related_flows_raw"):
            report.add(
                "ORPHAN_REQUIREMENT",
                "info",
                f"Use case {uc.id} has no related flow / verification edges",
                uc.id,
                provenance="declared",
                source_path=uc.source_ref.path if uc.source_ref else "",
                reason="No RelatedFlows / VF linkage",
            )
    for req in requirements:
        neighbors = [e for e in graph.edges if e.source == req.id or e.target == req.id]
        if not neighbors:
            report.add(
                "ORPHAN_REQUIREMENT",
                "info",
                f"Requirement-like node {req.id} has no edges",
                req.id,
                provenance="declared",
                source_path=req.source_ref.path if req.source_ref else "",
            )

    # Unmapped source files (exist, no module/verification edge of domain types)
    domain_file_edges = {
        EdgeType.IMPLEMENTED_IN,
        EdgeType.TESTED_BY,
        EdgeType.HAS_CONTRACT,
        EdgeType.HAS_BLOCK,
        EdgeType.LINKS_TO,
    }
    linked_files: set[str] = set()
    for e in graph.edges:
        if e.type in domain_file_edges:
            linked_files.add(e.source)
            linked_files.add(e.target)

    unmapped: list[Node] = []
    for f in files:
        if f.type != NodeType.SOURCE_FILE:
            continue
        if not f.properties.get("exists"):
            continue
        if f.properties.get("is_dir"):
            continue
        # Only count sources under src/ as unmapped interest
        path = str(f.properties.get("path") or "")
        if not path.startswith("src/"):
            continue
        if f.id not in linked_files:
            unmapped.append(f)
            report.add(
                "UNMAPPED_FILE",
                "info",
                f"Source file has no GRACE module edge: {path}",
                f.id,
                provenance="inferred",
                source_path=path,
                reason="File exists and was scanned but no M-* implemented_in/links_to",
            )

    # Ambiguous: free-text cross_link only, or multiple implemented_in for same module with missing
    for e in graph.edges:
        if e.type == EdgeType.CROSS_LINK:
            raw = (e.properties or {}).get("raw_relation") or e.description
            report.add(
                "AMBIGUOUS_LINK",
                "info",
                f"CrossLink kept as free-text relation: {raw!r}",
                e.source,
                provenance="declared",
                source_path=e.artifact_path,
                related=[e.target],
                raw_relation=raw,
                reason="Relation text not mapped to a stricter edge type",
            )
        if e.provenance == Provenance.INFERRED:
            report.add(
                "INFERRED_EDGE",
                "info",
                f"Inferred edge {e.source} -[{e.type}]-> {e.target} is not auto-confirmed",
                e.source,
                provenance="inferred",
                source_path=e.artifact_path,
                related=[e.target],
                edge_type=e.type,
            )

    broken = report.by_code("BROKEN_REFERENCE")
    by_sev: dict[str, int] = {}
    by_code: dict[str, int] = {}
    for f in report.findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
        by_code[f.code] = by_code.get(f.code, 0) + 1

    report.summary = {
        "findings": len(report.findings),
        "by_severity": by_sev,
        "by_code": by_code,
        "graph": graph.stats(),
        "modules": len(modules),
        "verifications": len(verifications),
        "use_cases": len(use_cases),
        "files": len(files),
        "missing_files": len(missing_files),
        "stub_modules": len(stub_modules),
        "unverified_modules": unverified,
        "broken_references": len(broken),
        "orphan_requirements": len(report.by_code("ORPHAN_REQUIREMENT")),
        "unmapped_files": len(unmapped),
        "ambiguous_links": len(report.by_code("AMBIGUOUS_LINK")),
    }
    return report


def _finding_lines(finding: GapFinding, graph: AtlasGraph) -> list[str]:
    from grace_atlas.exporters.notes import wikilink

    lines = [
        f"### `{finding.code}` — {finding.entity_id or '(no id)'}",
        "",
        f"- **Severity**: `{finding.severity}`",
        f"- **Provenance**: `{finding.provenance}`",
        f"- **Description**: {finding.message}",
    ]
    if finding.source_path:
        ln = f":{finding.source_line}" if finding.source_line else ""
        lines.append(f"- **Source**: `{finding.source_path}{ln}`")
    if finding.related:
        rel_bits = []
        for rid in finding.related:
            n = graph.get(rid)
            rel_bits.append(wikilink(n, rid) if n else f"`{rid}`")
        lines.append(f"- **Related**: {', '.join(rel_bits)}")
    if finding.details:
        for k, v in sorted(finding.details.items()):
            lines.append(f"- **{k}**: `{v}`")
    lines.append("")
    return lines


def render_diagnostics_pages(report: GapReport, graph: AtlasGraph) -> dict[str, str]:
    """Return vault-relative path → markdown content for Diagnostics/*."""
    from grace_atlas.exporters.markdown import GENERATED_BANNER

    def page(title: str, codes: list[str], intro: str) -> str:
        items = [f for f in report.findings if f.code in codes]
        lines = [
            GENERATED_BANNER,
            "",
            "---",
            "generated: true",
            "tags: [grace-atlas, grace/diagnostics, grace/index]",
            "---",
            "",
            f"# {title}",
            "",
            intro,
            "",
            f"Count: **{len(items)}**",
            "",
            "Legend: `declared` = from GRACE; `inferred` = heuristic (not auto-confirmed); "
            "`unresolved` = target missing or stub-only.",
            "",
        ]
        if not items:
            lines.append("_No findings in this category._")
            lines.append("")
            return "\n".join(lines)
        for f in sorted(items, key=lambda x: (x.severity, x.entity_id, x.message)):
            lines.extend(_finding_lines(f, graph))
        return "\n".join(lines)

    summary_lines = [
        GENERATED_BANNER,
        "",
        "---",
        "generated: true",
        "tags: [grace-atlas, grace/diagnostics, grace/index]",
        "---",
        "",
        "# Diagnostics Summary",
        "",
        "Read-only traceability diagnostics. Inferred links are **not** confirmed.",
        "",
        f"- Findings: **{report.summary.get('findings', 0)}**",
        f"- By severity: `{report.summary.get('by_severity', {})}`",
        f"- By code: `{report.summary.get('by_code', {})}`",
        "",
        "## Counters",
        "",
        f"- Modules: {report.summary.get('modules')}",
        f"- Verifications: {report.summary.get('verifications')}",
        f"- Use cases: {report.summary.get('use_cases')}",
        f"- Files: {report.summary.get('files')}",
        f"- Broken references: {report.summary.get('broken_references')}",
        f"- Orphan requirements/use-cases: {report.summary.get('orphan_requirements')}",
        f"- Unverified modules: {report.summary.get('unverified_modules')}",
        f"- Unmapped source files: {report.summary.get('unmapped_files')}",
        f"- Missing files: {report.summary.get('missing_files')}",
        f"- Ambiguous links: {report.summary.get('ambiguous_links')}",
        "",
        "## Reports",
        "",
        "- [[Diagnostics/Broken-References]]",
        "- [[Diagnostics/Orphan-Requirements]]",
        "- [[Diagnostics/Unverified-Modules]]",
        "- [[Diagnostics/Unmapped-Files]]",
        "- [[Diagnostics/Ambiguous-Links]]",
        "",
    ]

    return {
        "Diagnostics/Summary.md": "\n".join(summary_lines),
        "Diagnostics/Broken-References.md": page(
            "Broken References",
            ["BROKEN_REFERENCE", "MISSING_FILE", "STUB_MODULE"],
            "Declared paths or edge endpoints that cannot be resolved to real artifacts/nodes.",
        ),
        "Diagnostics/Orphan-Requirements.md": page(
            "Orphan Requirements / Use Cases",
            ["ORPHAN_REQUIREMENT"],
            "Use cases / requirement-like nodes without flow or verification linkage.",
        ),
        "Diagnostics/Unverified-Modules.md": page(
            "Unverified Modules",
            ["UNVERIFIED_MODULE", "MODULE_WITHOUT_SOURCE", "VERIFICATION_WITHOUT_TESTS", "VERIFICATION_BLOCKED"],
            "Modules without verification edges; verification entries without tests.",
        ),
        "Diagnostics/Unmapped-Files.md": page(
            "Unmapped Source Files",
            ["UNMAPPED_FILE"],
            "Source files under `src/` with no GRACE module edge (scan-only / orphan code).",
        ),
        "Diagnostics/Ambiguous-Links.md": page(
            "Ambiguous / Inferred Links",
            ["AMBIGUOUS_LINK", "INFERRED_EDGE", "STUB_VERIFICATION"],
            "Free-text CrossLinks and inferred edges — not auto-confirmed.",
        ),
    }


def render_gap_report_markdown(report: GapReport) -> str:
    """Single-file markdown summary (CLI / legacy)."""
    pages = render_diagnostics_pages(report, AtlasGraph())
    # Minimal CLI view
    import json

    lines = [
        "# GRACE Atlas — Traceability Gap Report",
        "",
        f"Findings: **{report.summary.get('findings', 0)}**",
        f"By severity: `{report.summary.get('by_severity', {})}`",
        f"By code: `{report.summary.get('by_code', {})}`",
        "",
        "```json",
        json.dumps(report.summary.get("graph") or {}, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    for f in report.findings[:100]:
        lines.append(f"- **{f.severity}** `{f.code}` {f.entity_id}: {f.message}")
    if len(report.findings) > 100:
        lines.append(f"- … and {len(report.findings) - 100} more")
    lines.append("")
    return "\n".join(lines)


def status_counts(graph: AtlasGraph, report: GapReport) -> dict[str, int]:
    stats = graph.stats()
    nbt = stats.get("nodes_by_type") or {}
    return {
        "requirements": nbt.get(NodeType.REQUIREMENT, 0) + nbt.get(NodeType.USE_CASE, 0),
        "modules": nbt.get(NodeType.MODULE, 0),
        "source_files": nbt.get(NodeType.SOURCE_FILE, 0),
        "verification_records": nbt.get(NodeType.VERIFICATION, 0),
        "tests": nbt.get(NodeType.TEST_FILE, 0),
        "edges": stats.get("edges", 0),
        "broken_references": report.summary.get("broken_references", 0),
        "orphan_requirements": report.summary.get("orphan_requirements", 0),
        "unverified_modules": report.summary.get("unverified_modules", 0),
        "unmapped_files": report.summary.get("unmapped_files", 0),
    }

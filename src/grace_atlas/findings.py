# FILE: tools/grace_atlas/src/grace_atlas/findings.py
# VERSION: 0.3.1
# PURPOSE: Human-oriented finding triage — categories, actions, filtering, grouping.

"""Gap finding triage and filtering for CLI + dashboards."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from grace_atlas.diagnostics import GapFinding, GapReport
from grace_atlas.model import AtlasGraph, NodeType

# Journey UC ids (declared Video2PPTX path)
USER_JOURNEY_IDS = frozenset(
    {
        "UC-001",
        "UC-002",
        "UC-005",
        "UC-008",
        "UC-009",
        "UC-010",
        "UC-013",
        "UC-016",
    }
)

# Map finding codes → category + default action + eligibility
CODE_META: dict[str, dict[str, str]] = {
    "MISSING_FILE": {
        "category": "broken_reference",
        "action": "Fix path in GRACE or restore file on disk",
        "eligibility": "actionable",
    },
    "BROKEN_REFERENCE": {
        "category": "broken_reference",
        "action": "Resolve missing edge endpoint or path",
        "eligibility": "actionable",
    },
    "STUB_MODULE": {
        "category": "stub",
        "action": "Define module fully in plan/graph or drop dead reference",
        "eligibility": "actionable",
    },
    "STUB_VERIFICATION": {
        "category": "stub",
        "action": "Add V-M-* entry in verification-plan or remove ref",
        "eligibility": "informational",
    },
    "MODULE_WITHOUT_VERIFICATION": {
        "category": "coverage",
        "action": "Add verification-ref / V-M entry",
        "eligibility": "actionable",
    },
    "MODULE_WITHOUT_SOURCE": {
        "category": "coverage",
        "action": "Add path/source for module or mark planned",
        "eligibility": "actionable",
    },
    "UNVERIFIED_MODULE": {
        "category": "coverage",
        "action": "Link module to V-M-*",
        "eligibility": "actionable",
    },
    "VERIFICATION_WITHOUT_TESTS": {
        "category": "coverage",
        "action": "Add test-files to verification entry",
        "eligibility": "actionable",
    },
    "VERIFICATION_BLOCKED": {
        "category": "status",
        "action": "Resolve blocked reason or document deferral",
        "eligibility": "actionable",
    },
    "ORPHAN_REQUIREMENT": {
        "category": "orphan",
        "action": "Link UC to RelatedFlows / VF or accept as isolated",
        "eligibility": "informational",
    },
    "UNMAPPED_FILE": {
        "category": "orphan",
        "action": "Add MODULE_CONTRACT LINKS or graph path",
        "eligibility": "informational",
    },
    "AMBIGUOUS_LINK": {
        "category": "ambiguity",
        "action": "Normalize CrossLink relation text or leave as free-form",
        "eligibility": "informational",
    },
    "INFERRED_EDGE": {
        "category": "inferred",
        "action": "Review inferred edge; do not treat as declared",
        "eligibility": "informational",
    },
    "module_without_verification": {
        "category": "coverage",
        "action": "Add verified_by for module",
        "eligibility": "actionable",
    },
    "module_without_source": {
        "category": "coverage",
        "action": "Add implemented_in path",
        "eligibility": "actionable",
    },
    "module_without_requirement": {
        "category": "coverage",
        "action": "Declare UC/requirement link if intentional product scope",
        "eligibility": "expected",
    },
    "requirement_without_module": {
        "category": "coverage",
        "action": "Link requirement to implementing module",
        "eligibility": "actionable",
    },
    "requirement_without_verification": {
        "category": "coverage",
        "action": "Add VF covering use case",
        "eligibility": "actionable",
    },
    "requirement_without_verification_flow": {
        "category": "coverage",
        "action": "Add RelatedFlows or VF USE_CASES link",
        "eligibility": "actionable",
    },
    "verification_without_test": {
        "category": "coverage",
        "action": "Attach test-files",
        "eligibility": "actionable",
    },
    "missing_evidence": {
        "category": "coverage",
        "action": "Record evidence under verification entry",
        "eligibility": "informational",
    },
    "missing_source_file": {
        "category": "broken_reference",
        "action": "Restore file or fix declared path",
        "eligibility": "actionable",
    },
}


@dataclass
class TriagedFinding:
    code: str
    severity: str
    message: str
    entity_id: str
    entity_type: str
    category: str
    source: str
    provenance: str
    current_phase_relevant: bool
    user_journey_relevant: bool
    suggested_action: str
    suppression_eligibility: str  # actionable | informational | expected | suppressed
    suppressed: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _entity_type(graph: AtlasGraph, entity_id: str) -> str:
    n = graph.get(entity_id)
    if n is None:
        return "unknown"
    return n.type


def _phase_ids(graph: AtlasGraph) -> set[str]:
    """Current phase = in_progress, else latest phase id."""
    phases = graph.nodes_by_type(NodeType.PHASE)
    in_prog = [
        p
        for p in phases
        if (p.status or "").lower() in {"in_progress", "in-progress", "active"}
    ]
    if in_prog:
        return {p.id for p in in_prog}
    if phases:
        # highest number
        def key(p):
            try:
                return int(p.id.split("-", 1)[1])
            except Exception:
                return -1

        return {max(phases, key=key).id}
    return set()


def _entity_touches_phase(graph: AtlasGraph, entity_id: str, phase_ids: set[str]) -> bool:
    if not phase_ids:
        return False
    if entity_id in phase_ids:
        return True
    n = graph.get(entity_id)
    if n and n.properties.get("phase") in phase_ids:
        return True
    # steps belonging to phase
    for e in graph.edges:
        if e.source in phase_ids and e.target == entity_id:
            return True
        if e.target in phase_ids and e.source == entity_id:
            return True
    return False


def _entity_touches_journey(entity_id: str, graph: AtlasGraph) -> bool:
    if entity_id in USER_JOURNEY_IDS:
        return True
    # VFs / modules linked to journey UCs
    for e in graph.edges:
        if e.target in USER_JOURNEY_IDS or e.source in USER_JOURNEY_IDS:
            if entity_id in {e.source, e.target}:
                return True
    return False


def triage_findings(
    graph: AtlasGraph,
    report: GapReport,
    *,
    suppress: Iterable[str] | None = None,
    expected_patterns: Iterable[str] | None = None,
) -> list[TriagedFinding]:
    suppress_set = set(suppress or [])
    expected_set = set(expected_patterns or [])
    phase_ids = _phase_ids(graph)
    out: list[TriagedFinding] = []

    for f in report.findings:
        meta = CODE_META.get(f.code, {})
        category = meta.get("category") or f.details.get("category") or "other"
        action = meta.get("action") or "Review finding"
        eligibility = meta.get("eligibility") or "informational"
        suppressed = f.code in suppress_set
        if f.code in expected_set and eligibility != "actionable":
            eligibility = "expected"
        if suppressed:
            eligibility = "suppressed"

        out.append(
            TriagedFinding(
                code=f.code,
                severity=f.severity,
                message=f.message,
                entity_id=f.entity_id,
                entity_type=_entity_type(graph, f.entity_id),
                category=category,
                source=f.source_path or f.details.get("source") or "",
                provenance=f.provenance,
                current_phase_relevant=_entity_touches_phase(graph, f.entity_id, phase_ids),
                user_journey_relevant=_entity_touches_journey(f.entity_id, graph),
                suggested_action=action,
                suppression_eligibility=eligibility,
                suppressed=suppressed,
                details=dict(f.details),
            )
        )
    return out


def filter_triaged(
    findings: list[TriagedFinding],
    *,
    severity: str | None = None,
    actionable: bool = False,
    current_phase: bool = False,
    user_journey: bool = False,
    include_suppressed: bool = False,
) -> list[TriagedFinding]:
    rows = findings
    if not include_suppressed:
        rows = [f for f in rows if not f.suppressed]
    if severity:
        rows = [f for f in rows if f.severity == severity]
    if actionable:
        rows = [f for f in rows if f.suppression_eligibility == "actionable"]
    if current_phase:
        rows = [f for f in rows if f.current_phase_relevant]
    if user_journey:
        rows = [f for f in rows if f.user_journey_relevant]
    return rows


def group_by_code(findings: list[TriagedFinding]) -> list[dict[str, Any]]:
    by: dict[str, list[TriagedFinding]] = defaultdict(list)
    for f in findings:
        by[f.code].append(f)
    rows: list[dict[str, Any]] = []
    for code in sorted(by.keys()):
        items = by[code]
        entities = sorted({i.entity_id for i in items if i.entity_id})
        sev = Counter(i.severity for i in items).most_common(1)[0][0]
        action = items[0].suggested_action
        rows.append(
            {
                "code": code,
                "severity": sev,
                "count": len(items),
                "affected_entities": entities[:20],
                "affected_count": len(entities),
                "suggested_action": action,
                "category": items[0].category,
                "eligibility": items[0].suppression_eligibility,
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["code"]))
    return rows


def top_actionable(findings: list[TriagedFinding], n: int = 5) -> list[TriagedFinding]:
    rows = filter_triaged(findings, actionable=True)
    # Prefer errors, journey, phase
    def score(f: TriagedFinding) -> tuple:
        sev = {"error": 0, "warning": 1, "info": 2}.get(f.severity, 3)
        return (sev, 0 if f.user_journey_relevant else 1, 0 if f.current_phase_relevant else 1, f.code, f.entity_id)

    return sorted(rows, key=score)[:n]

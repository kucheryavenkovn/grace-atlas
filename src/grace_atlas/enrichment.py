# FILE: tools/grace_atlas/src/grace_atlas/enrichment.py
# VERSION: 0.3.0
# PURPOSE: Annotate AtlasGraph nodes with workbench fields (gaps, reverse links, requirement_type).
# Read-only; does not invent FR/BR types when absent from source.

"""Post-parse enrichment for human workbench projection."""

from __future__ import annotations

from collections import defaultdict

from grace_atlas.diagnostics import GapReport
from grace_atlas.exporters.notes import note_wikilink_target
from grace_atlas.model import AtlasGraph, EdgeType, Node, NodeType


REQ_LIKE = {
    NodeType.REQUIREMENT,
    NodeType.USE_CASE,
    NodeType.CONSTRAINT,
    NodeType.RISK,
    NodeType.NON_GOAL,
}


def _wiki_prop(node: Node | None, node_id: str) -> str:
    if node is None:
        return f"[[Other/{node_id}]]"
    return f"[[{note_wikilink_target(node)}]]"


def enrich_graph(graph: AtlasGraph, report: GapReport) -> None:
    """Mutate node.properties for workbench frontmatter and cards."""
    # Index edges
    out: dict[str, list] = defaultdict(list)
    inc: dict[str, list] = defaultdict(list)
    for e in graph.edges:
        out[e.source].append(e)
        inc[e.target].append(e)

    # Gap index by entity
    gaps_by_entity: dict[str, list[str]] = defaultdict(list)
    for f in report.findings:
        if f.entity_id:
            gaps_by_entity[f.entity_id].append(f.code)

    for node in graph.nodes.values():
        props = node.properties
        props.setdefault("display_name", node.name or node.id)
        props["source_state"] = "declared" if not props.get("stub") else "unresolved"
        props["grace_type"] = _grace_type(node)

        # Requirement classification — only declared types, never invent FR/BR
        if node.type in REQ_LIKE:
            if node.type == NodeType.USE_CASE or node.id.startswith("UC-"):
                props["requirement_type"] = "use_case"
            elif node.id.startswith(("FR-", "BR-", "UR-", "NFR-", "AC-", "BRULE-")):
                # Only if ID itself declares the taxonomy
                prefix = node.id.split("-", 1)[0].lower()
                props["requirement_type"] = {
                    "fr": "functional",
                    "br": "business",
                    "ur": "user",
                    "nfr": "non_functional",
                    "ac": "acceptance_criterion",
                    "brule": "business_rule",
                }.get(prefix, "unspecified")
            else:
                props["requirement_type"] = "unspecified"
                props["requirement_type_note"] = (
                    "No BR/UR/FR/NFR/AC taxonomy in source; left as unspecified"
                )

        # Collect typed neighbor lists as wiki-link strings for properties
        depends_on: list[str] = []
        dependency_of: list[str] = []
        implemented_in: list[str] = []
        implemented_by: list[str] = []
        verified_by: list[str] = []
        verifies: list[str] = []
        tested_by: list[str] = []
        related_use_cases: list[str] = []
        planned_in: list[str] = []
        evidence: list[str] = []
        contracts: list[str] = []
        blocks: list[str] = []
        implements: list[str] = []

        for e in out.get(node.id, []):
            tgt = graph.get(e.target)
            w = _wiki_prop(tgt, e.target)
            if e.type == EdgeType.DEPENDS_ON:
                depends_on.append(w)
            elif e.type == EdgeType.IMPLEMENTED_IN:
                implemented_in.append(w)
            elif e.type == EdgeType.VERIFIED_BY:
                verified_by.append(w)
            elif e.type == EdgeType.TESTED_BY:
                tested_by.append(w)
            elif e.type == EdgeType.RELATED_FLOW:
                if e.target.startswith("UC-") or (tgt and tgt.type == NodeType.USE_CASE):
                    related_use_cases.append(w)
            elif e.type == EdgeType.BELONGS_TO:
                planned_in.append(w)
            elif e.type == EdgeType.PRODUCES_EVIDENCE:
                evidence.append(w)
            elif e.type == EdgeType.HAS_CONTRACT:
                contracts.append(w)
            elif e.type == EdgeType.HAS_BLOCK:
                blocks.append(w)
            elif e.type == EdgeType.IMPLEMENTS:
                implements.append(w)
            elif e.type == EdgeType.USES_USE_CASE:
                related_use_cases.append(w)

        for e in inc.get(node.id, []):
            src = graph.get(e.source)
            w = _wiki_prop(src, e.source)
            if e.type == EdgeType.DEPENDS_ON:
                dependency_of.append(w)
            elif e.type == EdgeType.IMPLEMENTED_IN:
                implemented_by.append(w)
            elif e.type == EdgeType.VERIFIED_BY:
                verifies.append(w)
            elif e.type == EdgeType.TESTED_BY and node.type == NodeType.TEST_FILE:
                pass
            elif e.type == EdgeType.USES_USE_CASE and node.type == NodeType.USE_CASE:
                # VF uses this UC
                pass
            elif e.type == EdgeType.IMPLEMENTS:
                # module implements this requirement
                if node.type in REQ_LIKE:
                    implemented_by.append(w)

        # Heuristic reverse: modules linked to UC via VF chain is hard; keep declared only

        if depends_on:
            props["depends_on"] = _uniq(depends_on)
        if dependency_of:
            props["dependency_of"] = _uniq(dependency_of)
        if implemented_in:
            props["implemented_in"] = _uniq(implemented_in)
        if implemented_by:
            props["implemented_by"] = _uniq(implemented_by)
        if verified_by:
            props["verified_by"] = _uniq(verified_by)
        if verifies:
            props["verifies"] = _uniq(verifies)
        if tested_by:
            props["tested_by"] = _uniq(tested_by)
        if related_use_cases:
            props["belongs_to_use_case"] = _uniq(related_use_cases)
        if planned_in:
            props["planned_in"] = _uniq(planned_in)
        if evidence:
            props["evidence"] = _uniq(evidence)
        if contracts:
            props["contracts"] = _uniq(contracts)
        if blocks:
            props["semantic_blocks"] = _uniq(blocks)
        if implements:
            props["implements"] = _uniq(implements)

        # Verification-specific
        if node.type == NodeType.VERIFICATION:
            props["test_files"] = list(props.get("test_files") or [])
            props["last_known_result"] = node.status or ""
            checks = props.get("checks") or []
            if checks:
                props["commands"] = checks[:20]

        # Priority for UC
        if node.type == NodeType.USE_CASE:
            props["priority"] = props.get("priority") or node.status or ""

        # Gaps
        gtypes = gaps_by_entity.get(node.id, [])
        # Local gap heuristics (declared absence)
        if node.type == NodeType.MODULE and not props.get("stub"):
            if not verified_by:
                gtypes.append("module_without_verification")
            if not implemented_in:
                gtypes.append("module_without_source")
            if not implements and not any(
                e.type == EdgeType.IMPLEMENTS for e in inc.get(node.id, [])
            ):
                # no declared requirement link — common in this project
                gtypes.append("module_without_requirement")
        if node.type in REQ_LIKE:
            if not implemented_by and not implements:
                # UC rarely has implements edge
                if node.type == NodeType.USE_CASE:
                    # Check VF coverage
                    has_vf = any(
                        e.type == EdgeType.USES_USE_CASE for e in inc.get(node.id, [])
                    )
                    if not has_vf and not related_use_cases:
                        gtypes.append("requirement_without_verification_flow")
                else:
                    gtypes.append("requirement_without_module")
            if not verified_by and node.type == NodeType.USE_CASE:
                has_vf = any(e.type == EdgeType.USES_USE_CASE for e in inc.get(node.id, []))
                if not has_vf:
                    gtypes.append("requirement_without_verification")
        if node.type == NodeType.VERIFICATION and not props.get("stub"):
            tests = props.get("test_files") or []
            if not tests and (node.status or "").lower() not in {"blocked", "planned"}:
                gtypes.append("verification_without_test")
            if not evidence and int(props.get("evidence_count") or 0) == 0:
                gtypes.append("missing_evidence")
        if node.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
            if props.get("missing") or props.get("exists") is False:
                gtypes.append("missing_source_file")

        gtypes = _uniq(gtypes)
        props["gap_types"] = gtypes
        props["has_traceability_gap"] = bool(gtypes)
        props["edge_count"] = len(out.get(node.id, [])) + len(inc.get(node.id, []))

        # source_file path for Bases (prefer repo-relative)
        if node.source_ref and node.source_ref.path:
            sp = str(node.source_ref.path).replace("\\", "/")
            # strip absolute prefix if it contains /docs/ or /src/
            for marker in ("/docs/", "/src/", "/tests/"):
                if marker in sp:
                    sp = sp[sp.index(marker) + 1 :]
                    break
            props["source_file"] = sp
            if node.source_ref.line_start:
                props["source_line"] = node.source_ref.line_start
        elif props.get("path"):
            props["source_file"] = str(props["path"]).replace("\\", "/")

        # Breadcrumbs-compatible optional fields (not required)
        if node.type == NodeType.STEP and props.get("phase"):
            phase = graph.get(props["phase"])
            if phase:
                props["bc_parent"] = f"[[{note_wikilink_target(phase)}]]"
        if planned_in:
            props["bc_parent"] = planned_in[0]


def _grace_type(node: Node) -> str:
    mapping = {
        NodeType.REQUIREMENT: "requirement",
        NodeType.USE_CASE: "use_case",
        NodeType.MODULE: "module",
        NodeType.SOURCE_FILE: "source_file",
        NodeType.TEST_FILE: "test_file",
        NodeType.VERIFICATION: "verification",
        NodeType.EVIDENCE: "evidence",
        NodeType.PHASE: "phase",
        NodeType.STEP: "step",
        NodeType.OPERATIONAL_PACKET: "operational_packet",
        NodeType.CONTRACT: "contract",
        NodeType.SEMANTIC_BLOCK: "semantic_block",
        NodeType.TECHNOLOGY: "technology",
        NodeType.CONSTRAINT: "requirement",
        NodeType.RISK: "requirement",
        NodeType.NON_GOAL: "requirement",
        NodeType.CRITICAL_FLOW: "verification",
        NodeType.DATA_FLOW: "requirement",
        NodeType.PHASE_GATE: "phase",
        NodeType.DEPLOYMENT: "module",
        NodeType.ACTOR: "requirement",
    }
    return mapping.get(node.type, "requirement")


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out

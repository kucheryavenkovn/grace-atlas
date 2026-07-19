# FILE: tools/grace_atlas/src/grace_atlas/parsers/verification_plan.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Parse verification-plan.xml critical flows, module verifications, gates, evidence.
#   SCOPE: VerificationPlan CriticalFlows / ModuleVerification / PhaseGates
#   DEPENDS: grace_atlas.model, _xmlutil
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Parse GRACE verification plan XML."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from grace_atlas.model import (
    AtlasGraph,
    Edge,
    EdgeType,
    Node,
    NodeType,
    Provenance,
)
from grace_atlas.parsers._xmlutil import (
    attr,
    build_line_map,
    child_text,
    local,
    parse_xml,
    short_desc,
    source_ref,
    split_ids,
    text_of,
)


def parse_verification_plan(path: Path, graph: AtlasGraph) -> None:
    root = parse_xml(path)
    line_map = build_line_map(path)
    rel = str(path)

    for section in root:
        tag = local(section.tag)
        if tag == "CriticalFlows":
            for vf in section:
                if local(vf.tag).startswith("VF-"):
                    _parse_critical_flow(vf, graph, path, line_map, rel)
        elif tag == "ModuleVerification":
            for vm in section:
                if local(vm.tag).startswith("V-M-") or local(vm.tag).startswith("V-"):
                    _parse_module_verification(vm, graph, path, line_map, rel)
        elif tag == "PhaseGates":
            for gate in section:
                gt = local(gate.tag)
                if gt.startswith("Gate-") or gt.startswith("gate-"):
                    _parse_phase_gate(gate, graph, path, line_map, rel)
        elif tag == "GlobalPolicy":
            graph.meta["verification_policy"] = short_desc(text_of(section), 800)


def _parse_critical_flow(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    vf_id = local(elem.tag)
    name = attr(elem, "NAME", "name", default=vf_id)
    use_cases = attr(elem, "USE_CASES", "use_cases", default="")
    data_flow = attr(elem, "DATA_FLOW", "data_flow", default="")
    priority = attr(elem, "PRIORITY", "priority", default="")
    scenario = child_text(elem, ("scenario", "SCENARIO"))
    expected = child_text(elem, ("expected-outcome", "expected_outcome", "expected"))

    graph.add_node(
        Node(
            id=vf_id,
            name=name,
            type=NodeType.CRITICAL_FLOW,
            description=short_desc(scenario or expected),
            status=priority,
            source="verification-plan",
            source_ref=source_ref(path, vf_id, line_map),
            properties={
                "use_cases": use_cases,
                "data_flow": data_flow,
                "priority": priority,
                "expected_outcome": short_desc(expected, 500),
            },
        )
    )

    for uc in split_ids(use_cases):
        if uc not in graph.nodes:
            graph.add_node(
                Node(id=uc, name=uc, type=NodeType.USE_CASE, source="verification-plan", properties={"stub": True})
            )
        graph.add_edge(
            Edge(
                source=vf_id,
                target=uc,
                type=EdgeType.USES_USE_CASE,
                relation_source="USE_CASES",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )

    for df in split_ids(data_flow):
        if df not in graph.nodes:
            graph.add_node(
                Node(id=df, name=df, type=NodeType.DATA_FLOW, source="verification-plan", properties={"stub": True})
            )
        graph.add_edge(
            Edge(
                source=vf_id,
                target=df,
                type=EdgeType.RELATED_FLOW,
                relation_source="DATA_FLOW",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )


def _parse_module_verification(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    vid = local(elem.tag)
    module = attr(elem, "MODULE", "module", default="")
    priority = attr(elem, "PRIORITY", "priority", default="")
    status = attr(elem, "STATUS", "status", default="")

    test_files: list[str] = []
    evidence_texts: list[str] = []
    checks: list[str] = []
    blocked_reason = ""

    for child in elem:
        ct = local(child.tag)
        if ct in {"test-files", "test_files"}:
            for f in child:
                if local(f.tag) in {"file", "file-1", "file-2"} or local(f.tag).startswith("file"):
                    raw = (f.text or "").strip().replace("\\", "/")
                    if raw:
                        test_files.append(raw)
                elif (f.text or "").strip():
                    test_files.append((f.text or "").strip().replace("\\", "/"))
        elif ct == "evidence":
            evidence_texts.append(short_desc(text_of(child), 500))
        elif ct in {"module-checks", "module_checks"}:
            for ch in child:
                t = text_of(ch)
                if t:
                    checks.append(short_desc(t, 300))
        elif ct in {"blocked-reason", "blocked_reason"}:
            blocked_reason = short_desc(text_of(child), 400)
        elif ct in {"scenarios",}:
            pass  # kept in raw properties if needed

    # Also collect file tags nested anywhere under test-files style
    for f_elem in elem.iter():
        if local(f_elem.tag) == "file" and (f_elem.text or "").strip():
            p = (f_elem.text or "").strip().replace("\\", "/")
            if p not in test_files:
                test_files.append(p)

    graph.add_node(
        Node(
            id=vid,
            name=vid,
            type=NodeType.VERIFICATION,
            description=short_desc("; ".join(checks[:3]) or blocked_reason or f"Verification for {module}"),
            status=status,
            source="verification-plan",
            source_ref=source_ref(path, vid, line_map),
            properties={
                "module": module,
                "priority": priority,
                "test_files": test_files,
                "checks": checks[:20],
                "blocked_reason": blocked_reason,
                "evidence_count": len(evidence_texts),
            },
        )
    )

    if module:
        if module not in graph.nodes:
            graph.add_node(
                Node(
                    id=module,
                    name=module,
                    type=NodeType.MODULE,
                    source="verification-plan",
                    properties={"stub": True},
                )
            )
        graph.add_edge(
            Edge(
                source=module,
                target=vid,
                type=EdgeType.VERIFIED_BY,
                relation_source="MODULE",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )

    for p in test_files:
        file_id = f"file:{p}"
        graph.add_node(
            Node(
                id=file_id,
                name=p,
                type=NodeType.TEST_FILE,
                source="verification-plan",
                properties={"path": p},
            )
        )
        graph.add_edge(
            Edge(
                source=vid,
                target=file_id,
                type=EdgeType.TESTED_BY,
                relation_source="test-files",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )
        if module:
            graph.add_edge(
                Edge(
                    source=module,
                    target=file_id,
                    type=EdgeType.TESTED_BY,
                    relation_source="test-files via verification",
                    provenance=Provenance.INFERRED,
                    artifact_path=rel,
                )
            )

    for i, ev in enumerate(evidence_texts, start=1):
        eid = f"evidence:{vid}:{i}"
        graph.add_node(
            Node(
                id=eid,
                name=f"Evidence {i} for {vid}",
                type=NodeType.EVIDENCE,
                description=ev,
                source="verification-plan",
                properties={"verification": vid},
            )
        )
        graph.add_edge(
            Edge(
                source=vid,
                target=eid,
                type=EdgeType.PRODUCES_EVIDENCE,
                relation_source="evidence",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )


def _parse_phase_gate(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    gid = local(elem.tag)
    status = attr(elem, "STATUS", "status", default="")
    body = short_desc(text_of(elem), 600)
    graph.add_node(
        Node(
            id=gid,
            name=gid,
            type=NodeType.PHASE_GATE,
            description=body,
            status=status,
            source="verification-plan",
            source_ref=source_ref(path, gid, line_map),
        )
    )
    # Link Gate-Phase-N → Phase-N
    if gid.startswith("Gate-Phase-"):
        phase_id = gid.replace("Gate-", "", 1)
        if phase_id not in graph.nodes:
            graph.add_node(
                Node(
                    id=phase_id,
                    name=phase_id,
                    type=NodeType.PHASE,
                    source="verification-plan",
                    properties={"stub": True},
                )
            )
        graph.add_edge(
            Edge(
                source=gid,
                target=phase_id,
                type=EdgeType.REFERS_TO,
                relation_source="PhaseGates",
                provenance=Provenance.INFERRED,
                artifact_path=rel,
            )
        )

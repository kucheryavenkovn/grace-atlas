# FILE: tools/grace_atlas/src/grace_atlas/parsers/requirements.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Parse requirements.xml into UseCase, Constraint, Risk, NonGoal, Actor nodes.
#   SCOPE: RequirementsAnalysis root
#   DEPENDS: grace_atlas.model, _xmlutil
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Parse GRACE requirements analysis XML."""

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


def parse_requirements(path: Path, graph: AtlasGraph) -> None:
    root = parse_xml(path)
    line_map = build_line_map(path)
    rel = str(path)

    # Project metadata
    for child in root:
        tag = local(child.tag)
        if tag == "Project":
            name = child_text(child, ("name", "NAME"), default="")
            if name:
                graph.meta["requirements_project"] = name
            ann = child_text(child, ("annotation",), default="")
            if ann:
                graph.meta["project_annotation"] = short_desc(ann, 800)
        elif tag == "Actors":
            for actor in child:
                aid = local(actor.tag)
                if aid.startswith("actor-") or local(actor.tag) == "actor":
                    node_id = aid if aid.startswith("actor-") else f"actor-{attr(actor, 'name', default=text_of(actor)[:40])}"
                    graph.add_node(
                        Node(
                            id=node_id,
                            name=text_of(actor) or node_id,
                            type=NodeType.ACTOR,
                            description=text_of(actor),
                            source="requirements",
                            source_ref=source_ref(path, node_id, line_map),
                        )
                    )
        elif tag == "UseCases":
            for uc in child:
                _parse_use_case(uc, graph, path, line_map, rel)
        elif tag == "Constraints":
            for c in child:
                _parse_simple(c, graph, NodeType.CONSTRAINT, path, line_map, "requirements")
        elif tag == "Risks":
            for c in child:
                _parse_simple(c, graph, NodeType.RISK, path, line_map, "requirements")
        elif tag == "NonGoals":
            for c in child:
                _parse_simple(c, graph, NodeType.NON_GOAL, path, line_map, "requirements")
        elif tag == "OpenQuestions":
            for c in child:
                _parse_simple(c, graph, NodeType.REQUIREMENT, path, line_map, "requirements", prefix="question")


def _parse_use_case(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    uc_id = local(elem.tag)
    if not uc_id.startswith("UC-"):
        uc_id = attr(elem, "id", "ID", default=uc_id)
    action = child_text(elem, ("Action", "action"))
    goal = child_text(elem, ("Goal", "goal"))
    actor = child_text(elem, ("Actor", "actor"))
    priority = child_text(elem, ("Priority", "priority"))
    pre = child_text(elem, ("Preconditions", "preconditions"))
    ac = child_text(elem, ("AcceptanceCriteria", "acceptance", "Acceptance"))
    flows_raw = child_text(elem, ("RelatedFlows", "related-flows", "related_flows"))

    name = action or goal or uc_id
    desc_parts = [p for p in (action, goal) if p]
    description = short_desc(" — ".join(desc_parts) if desc_parts else goal or action)

    graph.add_node(
        Node(
            id=uc_id,
            name=name,
            type=NodeType.USE_CASE,
            description=description,
            status=priority,
            source="requirements",
            source_ref=source_ref(path, uc_id, line_map),
            properties={
                "actor": actor,
                "priority": priority,
                "preconditions": short_desc(pre, 500),
                "acceptance_criteria": short_desc(ac, 800),
                "related_flows_raw": flows_raw,
            },
        )
    )

    for fid in split_ids(flows_raw):
        # DF-*, Phase-*, etc.
        if fid.startswith("DF-") or fid.startswith("Phase-") or fid.startswith("VF-"):
            if fid not in graph.nodes:
                ntype = (
                    NodeType.DATA_FLOW
                    if fid.startswith("DF-")
                    else NodeType.PHASE
                    if fid.startswith("Phase-")
                    else NodeType.CRITICAL_FLOW
                )
                graph.add_node(
                    Node(
                        id=fid,
                        name=fid,
                        type=ntype,
                        source="requirements",
                        source_ref=source_ref(path, fid, line_map),
                        properties={"stub": True},
                    )
                )
            graph.add_edge(
                Edge(
                    source=uc_id,
                    target=fid,
                    type=EdgeType.RELATED_FLOW,
                    relation_source="RelatedFlows",
                    provenance=Provenance.DECLARED,
                    description=f"{uc_id} related to {fid}",
                    artifact_path=rel,
                )
            )

    if actor:
        actor_id = f"actor-{actor.replace(' ', '-')}"
        if actor_id not in graph.nodes:
            graph.add_node(
                Node(
                    id=actor_id,
                    name=actor,
                    type=NodeType.ACTOR,
                    source="requirements",
                )
            )
        graph.add_edge(
            Edge(
                source=uc_id,
                target=actor_id,
                type=EdgeType.REFERS_TO,
                relation_source="Actor",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )


def _parse_simple(
    elem: ET.Element,
    graph: AtlasGraph,
    ntype: str,
    path: Path,
    line_map: dict[str, int],
    source: str,
    prefix: str = "",
) -> None:
    eid = local(elem.tag)
    body = text_of(elem)
    if not body and not eid:
        return
    node_id = eid if eid else f"{prefix or ntype}-{abs(hash(body)) % 10**8}"
    graph.add_node(
        Node(
            id=node_id,
            name=short_desc(body, 80) or node_id,
            type=ntype,
            description=short_desc(body, 600),
            source=source,
            source_ref=source_ref(path, node_id, line_map),
        )
    )

# FILE: tools/grace_atlas/src/grace_atlas/parsers/development_plan.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Parse development-plan.xml modules, data flows, phases, steps, deployment.
#   SCOPE: DevelopmentPlan Modules / DataFlow / ImplementationOrder / DeploymentScenarios
#   DEPENDS: grace_atlas.model, _xmlutil
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Parse GRACE development plan XML."""

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
    split_depends,
    text_of,
)


def parse_development_plan(path: Path, graph: AtlasGraph) -> None:
    root = parse_xml(path)
    line_map = build_line_map(path)
    rel = str(path)

    for section in root:
        tag = local(section.tag)
        if tag == "Modules":
            for mod in section:
                if local(mod.tag).startswith("M-"):
                    _parse_module(mod, graph, path, line_map, rel)
        elif tag == "DataFlow":
            for df in section:
                if local(df.tag).startswith("DF-"):
                    _parse_data_flow(df, graph, path, line_map, rel)
        elif tag == "ImplementationOrder":
            for phase in section:
                if local(phase.tag).startswith("Phase-"):
                    _parse_phase(phase, graph, path, line_map, rel)
        elif tag == "DeploymentScenarios":
            for ds in section:
                if local(ds.tag).startswith("DS-"):
                    _parse_deployment(ds, graph, path, line_map, rel)
        elif tag == "ArchitectureNotes":
            notes = short_desc(text_of(section), 1200)
            if notes:
                graph.meta["architecture_notes"] = notes


def _parse_module(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    mid = local(elem.tag)
    name = attr(elem, "NAME", "name", default=mid)
    mtype = attr(elem, "TYPE", "type", default="")
    status = attr(elem, "STATUS", "status", default="")
    layer = attr(elem, "LAYER", "layer", default="")
    order = attr(elem, "ORDER", "order", default="")

    purpose = ""
    contract = None
    for child in elem:
        if local(child.tag) == "contract":
            contract = child
            purpose = child_text(child, ("purpose", "PURPOSE")) or purpose
    if not purpose:
        purpose = child_text(elem, ("purpose", "PURPOSE"))

    source_paths: list[str] = []
    test_paths: list[str] = []
    for child in elem:
        if local(child.tag) != "target":
            continue
        for t in child:
            lt = local(t.tag)
            raw = (t.text or "").strip()
            if not raw:
                continue
            if lt == "source":
                for part in raw.split(","):
                    part = part.strip().replace("\\", "/")
                    if part:
                        source_paths.append(part)
            elif lt == "tests":
                for part in raw.split(","):
                    part = part.strip().replace("\\", "/")
                    if part:
                        test_paths.append(part)

    depends_raw = child_text(elem, ("depends", "DEPENDS"))
    vref = child_text(elem, ("verification-ref", "verification_ref"))

    node = graph.add_node(
        Node(
            id=mid,
            name=name,
            type=NodeType.MODULE,
            description=short_desc(purpose),
            status=status,
            source="development-plan",
            source_ref=source_ref(path, mid, line_map),
            properties={
                "module_type": mtype,
                "layer": layer,
                "order": order,
                "paths": source_paths,
                "test_paths": test_paths,
                "depends_raw": depends_raw,
                "verification_ref": vref,
                "has_contract": contract is not None,
            },
        )
    )
    # merge paths
    for key, values in (("paths", source_paths), ("test_paths", test_paths)):
        existing = list(node.properties.get(key) or [])
        for v in values:
            if v not in existing:
                existing.append(v)
        node.properties[key] = existing

    for dep in split_depends(depends_raw):
        if dep not in graph.nodes:
            graph.add_node(
                Node(id=dep, name=dep, type=NodeType.MODULE, source="development-plan", properties={"stub": True})
            )
        graph.add_edge(
            Edge(
                source=mid,
                target=dep,
                type=EdgeType.DEPENDS_ON,
                relation_source="depends",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )

    if vref:
        for vid in [v.strip() for v in vref.replace(",", " ").split() if v.strip()]:
            if vid not in graph.nodes:
                graph.add_node(
                    Node(
                        id=vid,
                        name=vid,
                        type=NodeType.VERIFICATION,
                        source="development-plan",
                        properties={"stub": True},
                    )
                )
            graph.add_edge(
                Edge(
                    source=mid,
                    target=vid,
                    type=EdgeType.VERIFIED_BY,
                    relation_source="verification-ref",
                    provenance=Provenance.DECLARED,
                    artifact_path=rel,
                )
            )

    for p in source_paths:
        file_id = f"file:{p}"
        graph.add_node(
            Node(id=file_id, name=p, type=NodeType.SOURCE_FILE, source="development-plan", properties={"path": p})
        )
        graph.add_edge(
            Edge(
                source=mid,
                target=file_id,
                type=EdgeType.IMPLEMENTED_IN,
                relation_source="target/source",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )

    for p in test_paths:
        file_id = f"file:{p}"
        graph.add_node(
            Node(id=file_id, name=p, type=NodeType.TEST_FILE, source="development-plan", properties={"path": p})
        )
        graph.add_edge(
            Edge(
                source=mid,
                target=file_id,
                type=EdgeType.TESTED_BY,
                relation_source="target/tests",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )


def _parse_data_flow(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    df_id = local(elem.tag)
    name = attr(elem, "NAME", "name", default=df_id)
    trigger = attr(elem, "TRIGGER", "trigger", default="")
    body = short_desc(text_of(elem), 800)
    graph.add_node(
        Node(
            id=df_id,
            name=name,
            type=NodeType.DATA_FLOW,
            description=body or trigger,
            source="development-plan",
            source_ref=source_ref(path, df_id, line_map),
            properties={"trigger": trigger},
        )
    )


def _parse_phase(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    phase_id = local(elem.tag)
    name = attr(elem, "name", "NAME", default=phase_id)
    status = attr(elem, "status", "STATUS", default="")
    goal = child_text(elem, ("goal", "GOAL"))
    plan_doc = child_text(elem, ("plan-doc", "plan_doc"))

    graph.add_node(
        Node(
            id=phase_id,
            name=name,
            type=NodeType.PHASE,
            description=short_desc(goal),
            status=status,
            source="development-plan",
            source_ref=source_ref(path, phase_id, line_map),
            properties={"plan_doc": plan_doc},
        )
    )
    if plan_doc:
        graph.add_edge(
            Edge(
                source=phase_id,
                target=f"file:{plan_doc}",
                type=EdgeType.DOCUMENTED_IN,
                relation_source="plan-doc",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )
        graph.add_node(
            Node(
                id=f"file:{plan_doc}",
                name=plan_doc,
                type=NodeType.SOURCE_FILE,
                source="development-plan",
                properties={"path": plan_doc},
            )
        )

    for child in elem:
        tag = local(child.tag)
        if not tag.startswith("step-"):
            continue
        step_id = tag
        step_name = attr(child, "name", "NAME", default=step_id)
        step_status = attr(child, "status", "STATUS", default="")
        vref = attr(child, "verification", "VERIFICATION", default="")
        body = short_desc(text_of(child), 600)
        graph.add_node(
            Node(
                id=step_id,
                name=step_name,
                type=NodeType.STEP,
                description=body,
                status=step_status,
                source="development-plan",
                source_ref=source_ref(path, step_id, line_map),
                properties={"phase": phase_id, "verification": vref},
            )
        )
        graph.add_edge(
            Edge(
                source=phase_id,
                target=step_id,
                type=EdgeType.CONTAINS,
                relation_source="ImplementationOrder",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )
        graph.add_edge(
            Edge(
                source=step_id,
                target=phase_id,
                type=EdgeType.BELONGS_TO,
                relation_source="ImplementationOrder",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )
        if vref:
            if vref not in graph.nodes:
                graph.add_node(
                    Node(
                        id=vref,
                        name=vref,
                        type=NodeType.VERIFICATION,
                        source="development-plan",
                        properties={"stub": True},
                    )
                )
            graph.add_edge(
                Edge(
                    source=step_id,
                    target=vref,
                    type=EdgeType.VERIFIED_BY,
                    relation_source="verification",
                    provenance=Provenance.DECLARED,
                    artifact_path=rel,
                )
            )


def _parse_deployment(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
) -> None:
    ds_id = local(elem.tag)
    name = attr(elem, "NAME", "name", default=ds_id)
    status = attr(elem, "STATUS", "status", default="")
    purpose = child_text(elem, ("purpose", "PURPOSE"))
    target = child_text(elem, ("target", "TARGET"))
    graph.add_node(
        Node(
            id=ds_id,
            name=name,
            type=NodeType.DEPLOYMENT,
            description=short_desc(purpose or target),
            status=status,
            source="development-plan",
            source_ref=source_ref(path, ds_id, line_map),
            properties={"target": target},
        )
    )

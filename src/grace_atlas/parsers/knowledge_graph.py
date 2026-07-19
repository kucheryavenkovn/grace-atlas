# FILE: tools/grace_atlas/src/grace_atlas/parsers/knowledge_graph.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Parse knowledge-graph.xml modules, paths, depends, verification-ref, CrossLinks.
#   SCOPE: KnowledgeGraph / Project / M-* / CrossLink
#   DEPENDS: grace_atlas.model, _xmlutil
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Parse GRACE knowledge graph XML."""

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


def parse_knowledge_graph(path: Path, graph: AtlasGraph) -> None:
    root = parse_xml(path)
    line_map = build_line_map(path)
    rel = str(path)

    project = root
    # May nest under Project
    for child in root:
        if local(child.tag) == "Project":
            project = child
            graph.meta.setdefault("kg_project", attr(child, "NAME", "name"))
            graph.meta.setdefault("kg_version", attr(child, "VERSION", "version"))
            break

    for elem in list(project):
        tag = local(elem.tag)
        if tag == "CrossLink":
            _parse_cross_link(elem, graph, rel)
            continue
        if tag.startswith("M-"):
            _parse_module(elem, graph, path, line_map, rel)
            # Nested submodules
            for sub in elem.iter():
                if sub is elem:
                    continue
                st = local(sub.tag)
                if st.startswith("M-"):
                    _parse_module(sub, graph, path, line_map, rel, parent=tag)


def _parse_module(
    elem: ET.Element,
    graph: AtlasGraph,
    path: Path,
    line_map: dict[str, int],
    rel: str,
    parent: str | None = None,
) -> None:
    mid = local(elem.tag)
    name = attr(elem, "NAME", "name", default=mid)
    mtype = attr(elem, "TYPE", "type", default="")
    status = attr(elem, "STATUS", "status", default="")
    purpose = child_text(elem, ("purpose", "PURPOSE")) or attr(elem, "PURPOSE", default="")

    # Multiple <path> children possible
    paths: list[str] = []
    for child in elem:
        if local(child.tag) == "path" and (child.text or "").strip():
            paths.append((child.text or "").strip().replace("\\", "/"))

    depends_raw = child_text(elem, ("depends", "DEPENDS"))
    vref = child_text(elem, ("verification-ref", "verification_ref", "VERIFICATION-REF"))

    node = graph.add_node(
        Node(
            id=mid,
            name=name,
            type=NodeType.MODULE,
            description=short_desc(purpose),
            status=status,
            source="knowledge-graph",
            source_ref=source_ref(path, mid, line_map),
            properties={
                "module_type": mtype,
                "paths": paths,
                "depends_raw": depends_raw,
                "verification_ref": vref,
                "parent_module": parent or "",
            },
        )
    )
    # merge paths if re-added from plan
    if paths:
        existing_paths = list(node.properties.get("paths") or [])
        for p in paths:
            if p not in existing_paths:
                existing_paths.append(p)
        node.properties["paths"] = existing_paths

    for dep in split_depends(depends_raw):
        if dep not in graph.nodes:
            graph.add_node(
                Node(
                    id=dep,
                    name=dep,
                    type=NodeType.MODULE,
                    source="knowledge-graph",
                    properties={"stub": True},
                )
            )
        graph.add_edge(
            Edge(
                source=mid,
                target=dep,
                type=EdgeType.DEPENDS_ON,
                relation_source="depends",
                provenance=Provenance.DECLARED,
                description=f"{mid} depends on {dep}",
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
                        source="knowledge-graph",
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

    for p in paths:
        file_id = f"file:{p}"
        is_test = "/test" in f"/{p.lower()}" or p.lower().startswith("tests/")
        ntype = NodeType.TEST_FILE if is_test else NodeType.SOURCE_FILE
        graph.add_node(
            Node(
                id=file_id,
                name=p,
                type=ntype,
                source="knowledge-graph",
                properties={"path": p},
            )
        )
        graph.add_edge(
            Edge(
                source=mid,
                target=file_id,
                type=EdgeType.IMPLEMENTED_IN,
                relation_source="path",
                provenance=Provenance.DECLARED,
                description=f"{mid} implemented in {p}",
                artifact_path=rel,
            )
        )

    if parent:
        graph.add_edge(
            Edge(
                source=parent,
                target=mid,
                type=EdgeType.CONTAINS,
                relation_source="submodules",
                provenance=Provenance.DECLARED,
                artifact_path=rel,
            )
        )


def _parse_cross_link(elem: ET.Element, graph: AtlasGraph, rel: str) -> None:
    src = attr(elem, "from", "FROM", "source")
    tgt = attr(elem, "to", "TO", "target")
    relation = attr(elem, "relation", "RELATION", "type", default="cross_link")
    if not src or not tgt:
        return
    for nid, label in ((src, src), (tgt, tgt)):
        if nid not in graph.nodes:
            ntype = NodeType.MODULE if nid.startswith("M-") else NodeType.REQUIREMENT
            graph.add_node(
                Node(
                    id=nid,
                    name=label,
                    type=ntype,
                    source="knowledge-graph",
                    properties={"stub": True},
                )
            )
    # Map free-text relation into a typed edge when possible.
    edge_type = _map_relation(relation)
    graph.add_edge(
        Edge(
            source=src,
            target=tgt,
            type=edge_type,
            relation_source="CrossLink",
            provenance=Provenance.DECLARED,
            description=relation,
            artifact_path=rel,
            properties={"raw_relation": relation},
        )
    )


def _map_relation(relation: str) -> str:
    r = (relation or "").lower()
    if "depend" in r:
        return EdgeType.DEPENDS_ON
    if "implement" in r:
        return EdgeType.IMPLEMENTS
    if "verif" in r or "test" in r:
        return EdgeType.VERIFIED_BY
    if "contain" in r or "own" in r:
        return EdgeType.CONTAINS
    if "call" in r or "orchestr" in r or "delegat" in r or "uses" in r or "reads" in r or "feeds" in r:
        return EdgeType.REFERS_TO
    return EdgeType.CROSS_LINK

# FILE: tools/grace_atlas/src/grace_atlas/trace.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Terminal traceability tree for a selected entity id.
#   SCOPE: BFS/DFS limited walk along implements/depends/implemented_in/verified_by/tested_by
#   DEPENDS: grace_atlas.model
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""CLI trace tree rendering."""

from __future__ import annotations

from grace_atlas.model import AtlasGraph, EdgeType

# Preferred edge order for display
TRACE_EDGE_ORDER = [
    EdgeType.IMPLEMENTS,
    EdgeType.DEPENDS_ON,
    EdgeType.IMPLEMENTED_IN,
    EdgeType.VERIFIED_BY,
    EdgeType.TESTED_BY,
    EdgeType.PRODUCES_EVIDENCE,
    EdgeType.RELATED_FLOW,
    EdgeType.USES_USE_CASE,
    EdgeType.CONTAINS,
    EdgeType.BELONGS_TO,
    EdgeType.HAS_CONTRACT,
    EdgeType.CROSS_LINK,
    EdgeType.REFERS_TO,
    EdgeType.LINKS_TO,
]


def format_trace(graph: AtlasGraph, entity_id: str, *, max_depth: int = 4, max_children: int = 12) -> str:
    if entity_id not in graph.nodes:
        # fuzzy: try case-sensitive exact among keys
        candidates = [k for k in graph.nodes if k.upper() == entity_id.upper()]
        if len(candidates) == 1:
            entity_id = candidates[0]
        else:
            return f"Entity not found: {entity_id}\n"

    lines: list[str] = []
    node = graph.nodes[entity_id]
    lines.append(f"{node.id}  [{node.type}]  status={node.status or '?'}")
    if node.description:
        lines.append(f"  {node.description[:200]}")
    _walk(graph, entity_id, lines, prefix="", depth=0, max_depth=max_depth, max_children=max_children, seen={entity_id})
    return "\n".join(lines) + "\n"


def _walk(
    graph: AtlasGraph,
    node_id: str,
    lines: list[str],
    *,
    prefix: str,
    depth: int,
    max_depth: int,
    max_children: int,
    seen: set[str],
) -> None:
    if depth >= max_depth:
        return
    outgoing = [e for e in graph.edges if e.source == node_id]
    # stable order by preferred type then target
    order_index = {t: i for i, t in enumerate(TRACE_EDGE_ORDER)}
    outgoing.sort(key=lambda e: (order_index.get(e.type, 999), e.type, e.target))

    # Dedup by (type, target)
    seen_et: set[tuple[str, str]] = set()
    children = []
    for e in outgoing:
        key = (e.type, e.target)
        if key in seen_et:
            continue
        seen_et.add(key)
        children.append(e)
        if len(children) >= max_children:
            break

    for i, e in enumerate(children):
        last = i == len(children) - 1
        branch = "└── " if last else "├── "
        cont = "    " if last else "│   "
        tgt = graph.get(e.target)
        label = e.target
        extra = ""
        if tgt and tgt.type in {"SourceFile", "TestFile"}:
            label = tgt.properties.get("path") or tgt.name or e.target
        elif tgt:
            label = tgt.id
        prov = f" ({e.provenance.value})" if e.provenance.value != "declared" else ""
        lines.append(f"{prefix}{branch}{e.type}: {label}{prov}{extra}")
        if e.target in seen:
            continue
        seen2 = set(seen)
        seen2.add(e.target)
        _walk(
            graph,
            e.target,
            lines,
            prefix=prefix + cont,
            depth=depth + 1,
            max_depth=max_depth,
            max_children=max_children,
            seen=seen2,
        )

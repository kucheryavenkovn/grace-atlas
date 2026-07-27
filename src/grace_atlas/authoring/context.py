# FILE: src/grace_atlas/authoring/context.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Build minimal evidence-backed authoring context from AtlasGraph.
#   SCOPE: deterministic bounded breadth-first traversal; no LLM or filesystem writes.
#   DEPENDS: grace_atlas.model, authoring.models
#   LINKS: M-AUTHORING-CONTEXT; G3
#   ROLE: APPLICATION
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   build_entity_context - one entity + bounded neighbors + source refs
#   evidence_from_context - trace references for drafts
# END_MODULE_MAP

"""Minimal-context builder used by standalone authoring and future GUI."""

from __future__ import annotations

from collections import deque
from typing import Any

from grace_atlas.authoring.models import EvidenceRef
from grace_atlas.model import AtlasGraph, Node


def _node_dict(node: Node) -> dict[str, Any]:
    return {
        "id": node.id,
        "type": node.type,
        "name": node.name,
        "description": node.description,
        "status": node.status,
        "properties": node.properties,
        "sourceRef": node.source_ref.as_dict() if node.source_ref else None,
    }


def build_entity_context(
    graph: AtlasGraph,
    entity_ids: list[str] | tuple[str, ...],
    *,
    depth: int = 2,
    max_nodes: int = 40,
) -> dict[str, Any]:
    missing = [entity_id for entity_id in entity_ids if entity_id not in graph.nodes]
    if missing:
        raise KeyError(", ".join(missing))

    queue = deque((entity_id, 0) for entity_id in entity_ids)
    seen: set[str] = set()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()

    while queue and len(nodes) < max_nodes:
        current, level = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        nodes.append(_node_dict(graph.nodes[current]))
        if level >= depth:
            continue
        for edge, neighbor in sorted(graph.neighbors(current), key=lambda pair: pair[0].id):
            if edge.id not in edge_ids:
                edge_ids.add(edge.id)
                edges.append(
                    {
                        "source": edge.source,
                        "target": edge.target,
                        "relation": edge.type,
                        "provenance": edge.provenance.value,
                        "description": edge.description,
                    }
                )
            if neighbor.id not in seen:
                queue.append((neighbor.id, level + 1))

    return {
        "roots": list(entity_ids),
        "depth": depth,
        "truncated": bool(queue),
        "nodes": nodes,
        "edges": edges,
    }


def evidence_from_context(context: dict[str, Any]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for node in context.get("nodes") or []:
        source = node.get("sourceRef") or {}
        refs.append(
            EvidenceRef(
                entity_id=str(node.get("id") or ""),
                source_path=str(source.get("path") or ""),
                line_start=source.get("line_start"),
                line_end=source.get("line_end"),
                excerpt=str(node.get("description") or node.get("name") or "")[:500],
            )
        )
    return refs

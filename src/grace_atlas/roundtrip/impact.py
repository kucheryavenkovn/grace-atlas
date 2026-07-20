# FILE: tools/grace_atlas/src/grace_atlas/roundtrip/impact.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Impact analysis traversal over AtlasGraph with explanations.
#   SCOPE: ImpactQuery, BFS by relations, categorized affected sets
#   DEPENDS: model
#   LINKS: Phase 3D
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Impact analysis engine."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from grace_atlas.model import AtlasGraph, NodeType


DEFAULT_RELATIONS = [
    "implements",
    "implemented_in",
    "depends_on",
    "verified_by",
    "tested_by",
    "related_flow",
    "uses_use_case",
    "contains",
    "belongs_to",
    "planned_in",
    "produces_evidence",
    "has_contract",
    "has_block",
    "cross_link",
    "refers_to",
    "links_to",
]


def impact_query(
    graph: AtlasGraph,
    *,
    roots: list[str],
    direction: str = "both",
    relation_types: list[str] | None = None,
    max_depth: int = 3,
    include_requirements: bool = True,
    include_verification: bool = True,
    include_development: bool = True,
) -> dict[str, Any]:
    rel_set = set(relation_types or DEFAULT_RELATIONS)
    # adjacency
    out_adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    in_adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in graph.edges:
        if e.type not in rel_set:
            continue
        out_adj[e.source].append((e.target, e.type))
        in_adj[e.target].append((e.source, e.type))

    resolved_roots: list[str] = []
    for r in roots:
        if r in graph.nodes:
            resolved_roots.append(r)
        else:
            hits = [k for k in graph.nodes if k.upper() == r.upper()]
            if hits:
                resolved_roots.append(hits[0])

    dist: dict[str, int] = {}
    parent_edge: dict[str, tuple[str, str]] = {}  # node -> (via_node, relation)
    q: deque[tuple[str, int]] = deque()
    for r in resolved_roots:
        dist[r] = 0
        q.append((r, 0))

    while q:
        node, d = q.popleft()
        if d >= max_depth:
            continue
        neighbors: list[tuple[str, str]] = []
        if direction in {"outgoing", "both"}:
            neighbors.extend(out_adj.get(node, []))
        if direction in {"incoming", "both"}:
            neighbors.extend(in_adj.get(node, []))
        for nb, rel in neighbors:
            if nb in dist:
                continue
            if nb not in graph.nodes:
                continue
            dist[nb] = d + 1
            parent_edge[nb] = (node, rel)
            q.append((nb, d + 1))

    directly = sorted([n for n, d in dist.items() if d == 1])
    transitive = sorted([n for n, d in dist.items() if d > 1])

    def _by_types(types: set[str]) -> list[str]:
        return sorted(n for n in dist if n not in resolved_roots and graph.nodes[n].type in types)

    req_types = {NodeType.REQUIREMENT, NodeType.USE_CASE, NodeType.CONSTRAINT, NodeType.RISK}
    ver_types = {NodeType.VERIFICATION, NodeType.TEST_FILE, NodeType.EVIDENCE, NodeType.CRITICAL_FLOW}
    dev_types = {NodeType.PHASE, NodeType.STEP, NodeType.OPERATIONAL_PACKET}

    explanations: list[str] = []
    for n in list(directly)[:30] + list(transitive)[:30]:
        chain = [n]
        cur = n
        guard = 0
        while cur in parent_edge and guard < 12:
            via, rel = parent_edge[cur]
            chain.append(f"-[{rel}]-")
            chain.append(via)
            cur = via
            guard += 1
        chain_s = " ".join(reversed(chain))
        explanations.append(f"{n} affected because: {chain_s}")

    result: dict[str, Any] = {
        "roots": resolved_roots,
        "direction": direction,
        "maxDepth": max_depth,
        "directlyAffected": directly,
        "transitivelyAffected": transitive,
        "modules": _by_types({NodeType.MODULE}),
        "files": _by_types({NodeType.SOURCE_FILE, NodeType.TEST_FILE}),
        "requirements": _by_types(req_types) if include_requirements else [],
        "useCases": _by_types({NodeType.USE_CASE}) if include_requirements else [],
        "tests": _by_types({NodeType.TEST_FILE}) if include_verification else [],
        "verification": _by_types({NodeType.VERIFICATION, NodeType.CRITICAL_FLOW})
        if include_verification
        else [],
        "evidence": _by_types({NodeType.EVIDENCE}) if include_verification else [],
        "phases": _by_types(dev_types) if include_development else [],
        "operationalPackets": _by_types({NodeType.OPERATIONAL_PACKET}) if include_development else [],
        "explanations": explanations,
        "distances": dist,
    }
    return result

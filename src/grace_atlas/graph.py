# FILE: tools/grace_atlas/src/grace_atlas/graph.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: High-level graph build orchestration and serialization helpers.
#   SCOPE: build_graph, export JSON snapshot
#   DEPENDS: discovery, parsers, diagnostics, config
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   build_graph - discover + parse into AtlasGraph
#   graph_to_jsonable - serializable dict
# END_MODULE_MAP

"""Graph build orchestration."""

from __future__ import annotations

from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.discovery import GraceArtifacts, discover_artifacts
from grace_atlas.model import AtlasGraph
from grace_atlas.parsers import parse_all


def build_graph(
    config: AtlasConfig,
    *,
    include_source: bool = True,
    artifacts: GraceArtifacts | None = None,
) -> tuple[AtlasGraph, GraceArtifacts]:
    """Discover GRACE artifacts and build the normalized graph."""
    arts = artifacts or discover_artifacts(config)
    graph = parse_all(arts, config, include_source=include_source)
    return graph, arts


def graph_to_jsonable(graph: AtlasGraph) -> dict[str, Any]:
    return {
        "meta": graph.meta,
        "stats": graph.stats(),
        "nodes": [n.as_dict() for n in graph.nodes.values()],
        "edges": [e.as_dict() for e in graph.edges],
    }

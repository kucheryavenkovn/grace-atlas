# FILE: tools/grace_atlas/src/grace_atlas/parsers/__init__.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: XML and source parsers that populate AtlasGraph from real GRACE artifacts.
#   SCOPE: re-export parse entry points
#   DEPENDS: grace_atlas.parsers.*
#   LINKS: tools/grace_atlas
#   ROLE: BARREL
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   parse_all - run all artifact parsers into a graph
# END_MODULE_MAP

from __future__ import annotations

from pathlib import Path

from grace_atlas.config import AtlasConfig
from grace_atlas.discovery import GraceArtifacts
from grace_atlas.model import AtlasGraph
from grace_atlas.parsers.development_plan import parse_development_plan
from grace_atlas.parsers.knowledge_graph import parse_knowledge_graph
from grace_atlas.parsers.operational_packets import parse_operational_packets
from grace_atlas.parsers.requirements import parse_requirements
from grace_atlas.parsers.source_markup import parse_source_markup
from grace_atlas.parsers.technology import parse_technology
from grace_atlas.parsers.verification_plan import parse_verification_plan
from grace_atlas.source_links import link_source_and_test_files


def parse_all(
    artifacts: GraceArtifacts,
    config: AtlasConfig,
    *,
    include_source: bool = True,
) -> AtlasGraph:
    """Parse all discovered artifacts into a single AtlasGraph."""
    graph = AtlasGraph()
    graph.meta["project_name"] = config.project_name
    graph.meta["repo_root"] = str(config.repo_root)
    graph.meta["artifacts"] = artifacts.as_dict()

    if artifacts.requirements:
        parse_requirements(artifacts.requirements, graph)
    if artifacts.development_plan:
        parse_development_plan(artifacts.development_plan, graph)
    if artifacts.knowledge_graph:
        parse_knowledge_graph(artifacts.knowledge_graph, graph)
    if artifacts.verification_plan:
        parse_verification_plan(artifacts.verification_plan, graph)
    if artifacts.operational_packets:
        parse_operational_packets(artifacts.operational_packets, graph)
    if artifacts.technology:
        parse_technology(artifacts.technology, graph)

    if include_source:
        parse_source_markup(config, graph)
    # Always resolve declared file paths (existence) even without markup scan.
    link_source_and_test_files(config, graph)

    return graph


__all__ = ["parse_all"]

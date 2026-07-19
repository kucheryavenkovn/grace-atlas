# FILE: tools/grace_atlas/src/grace_atlas/model.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Normalized internal graph model for GRACE entities and relations.
#   SCOPE: Node, Edge, AtlasGraph dataclasses and node/edge type constants
#   DEPENDS: dataclasses, typing
#   LINKS: tools/grace_atlas
#   ROLE: TYPES
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   NodeType - known node type string constants
#   EdgeType - known edge type string constants
#   Provenance - declared vs inferred
#   Node - graph node
#   Edge - graph edge
#   SourceRef - path + optional line range for an artifact
#   AtlasGraph - container for nodes and edges
# END_MODULE_MAP

"""Normalized GRACE Atlas graph model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# START_BLOCK_NODE_TYPES
class NodeType:
    """Node type labels present when real data exists (not forced empty shells)."""

    REQUIREMENT = "Requirement"
    USE_CASE = "UseCase"
    MODULE = "Module"
    VERIFICATION = "Verification"
    CRITICAL_FLOW = "CriticalFlow"
    DATA_FLOW = "DataFlow"
    PHASE = "Phase"
    STEP = "Step"
    OPERATIONAL_PACKET = "OperationalPacket"
    SOURCE_FILE = "SourceFile"
    TEST_FILE = "TestFile"
    CONTRACT = "Contract"
    SEMANTIC_BLOCK = "SemanticBlock"
    TECHNOLOGY = "Technology"
    EVIDENCE = "Evidence"
    CONSTRAINT = "Constraint"
    RISK = "Risk"
    NON_GOAL = "NonGoal"
    PHASE_GATE = "PhaseGate"
    DEPLOYMENT = "Deployment"
    ACTOR = "Actor"


class EdgeType:
    """Normalized relation types (preserve semantics from sources)."""

    IMPLEMENTS = "implements"
    IMPLEMENTED_IN = "implemented_in"
    DEPENDS_ON = "depends_on"
    VERIFIED_BY = "verified_by"
    TESTED_BY = "tested_by"
    PLANNED_IN = "planned_in"
    BELONGS_TO = "belongs_to"
    CONTAINS = "contains"
    PRODUCES_EVIDENCE = "produces_evidence"
    CHANGED_BY = "changed_by"
    CONSTRAINED_BY = "constrained_by"
    RELATED_FLOW = "related_flow"
    USES_USE_CASE = "uses_use_case"
    CROSS_LINK = "cross_link"
    LINKS_TO = "links_to"
    TRIGGERS = "triggers"
    DOCUMENTED_IN = "documented_in"
    HAS_CONTRACT = "has_contract"
    HAS_BLOCK = "has_block"
    REFERS_TO = "refers_to"


class Provenance(str, Enum):
    DECLARED = "declared"
    INFERRED = "inferred"
# END_BLOCK_NODE_TYPES


# START_BLOCK_CORE_TYPES
@dataclass(slots=True)
class SourceRef:
    """Location of the data that produced a node or edge."""

    path: str
    line_start: int | None = None
    line_end: int | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"path": self.path}
        if self.line_start is not None:
            d["line_start"] = self.line_start
        if self.line_end is not None:
            d["line_end"] = self.line_end
        return d


@dataclass
class Node:
    """Normalized graph node."""

    id: str
    name: str
    type: str
    description: str = ""
    status: str = ""
    source: str = ""
    source_ref: SourceRef | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "status": self.status,
            "source": self.source,
            "source_ref": self.source_ref.as_dict() if self.source_ref else None,
            "properties": dict(self.properties),
        }


@dataclass
class Edge:
    """Normalized graph edge."""

    source: str
    target: str
    type: str
    relation_source: str = ""
    provenance: Provenance = Provenance.DECLARED
    description: str = ""
    artifact_path: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}|{self.type}|{self.target}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "relation_source": self.relation_source,
            "provenance": self.provenance.value,
            "description": self.description,
            "artifact_path": self.artifact_path,
            "properties": dict(self.properties),
        }


@dataclass
class AtlasGraph:
    """In-memory graph of GRACE entities and relations."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    _edge_keys: set[str] = field(default_factory=set, repr=False)

    def add_node(self, node: Node, *, merge: bool = True) -> Node:
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return node
        if not merge:
            return existing
        # Prefer non-empty fields from the new node without wiping earlier data.
        if node.name and (not existing.name or existing.name == existing.id):
            existing.name = node.name
        if node.description and len(node.description) > len(existing.description or ""):
            existing.description = node.description
        if node.status and not existing.status:
            existing.status = node.status
        if node.source and not existing.source:
            existing.source = node.source
        if node.source_ref and not existing.source_ref:
            existing.source_ref = node.source_ref
        for k, v in node.properties.items():
            if k not in existing.properties or not existing.properties[k]:
                existing.properties[k] = v
            elif isinstance(v, list) and isinstance(existing.properties.get(k), list):
                seen = set(existing.properties[k])
                for item in v:
                    if item not in seen:
                        existing.properties[k].append(item)
                        seen.add(item)
        return existing

    def add_edge(self, edge: Edge) -> Edge | None:
        key = edge.id
        if key in self._edge_keys:
            return None
        self._edge_keys.add(key)
        self.edges.append(edge)
        return edge

    def get(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def nodes_by_type(self, node_type: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.type == node_type]

    def neighbors(self, node_id: str) -> list[tuple[Edge, Node]]:
        out: list[tuple[Edge, Node]] = []
        for e in self.edges:
            if e.source == node_id and e.target in self.nodes:
                out.append((e, self.nodes[e.target]))
            elif e.target == node_id and e.source in self.nodes:
                out.append((e, self.nodes[e.source]))
        return out

    def stats(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for n in self.nodes.values():
            by_type[n.type] = by_type.get(n.type, 0) + 1
        edge_by_type: dict[str, int] = {}
        for e in self.edges:
            edge_by_type[e.type] = edge_by_type.get(e.type, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "nodes_by_type": dict(sorted(by_type.items())),
            "edges_by_type": dict(sorted(edge_by_type.items())),
        }
# END_BLOCK_CORE_TYPES

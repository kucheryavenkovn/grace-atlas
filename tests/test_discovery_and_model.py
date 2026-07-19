# FILE: tools/grace_atlas/tests/test_discovery_and_model.py
# VERSION: 0.2.0

from __future__ import annotations

from pathlib import Path

from grace_atlas.config import load_config
from grace_atlas.discovery import discover_artifacts
from grace_atlas.model import AtlasGraph, Edge, EdgeType, Node, NodeType, Provenance


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_discover_real_repo_artifacts():
    root = _repo_root()
    cfg = load_config(repo_root=root)
    arts = discover_artifacts(cfg)
    assert arts.requirements is not None
    assert arts.requirements.name == "requirements.xml"
    assert arts.development_plan is not None
    assert arts.knowledge_graph is not None
    assert arts.verification_plan is not None


def test_graph_add_node_merge():
    g = AtlasGraph()
    g.add_node(Node(id="M-X", name="X", type=NodeType.MODULE, description="a", properties={"paths": ["a.py"]}))
    g.add_node(
        Node(
            id="M-X",
            name="X full",
            type=NodeType.MODULE,
            description="longer description",
            status="implemented",
            properties={"paths": ["b.py"]},
        )
    )
    n = g.get("M-X")
    assert n is not None
    assert n.description == "longer description"
    assert n.status == "implemented"
    assert n.properties["paths"] == ["a.py", "b.py"]


def test_graph_edge_dedup():
    g = AtlasGraph()
    g.add_node(Node(id="A", name="A", type=NodeType.MODULE))
    g.add_node(Node(id="B", name="B", type=NodeType.MODULE))
    e1 = g.add_edge(Edge(source="A", target="B", type=EdgeType.DEPENDS_ON, provenance=Provenance.DECLARED))
    e2 = g.add_edge(Edge(source="A", target="B", type=EdgeType.DEPENDS_ON, provenance=Provenance.DECLARED))
    assert e1 is not None
    assert e2 is None
    assert len(g.edges) == 1

# FILE: tools/grace_atlas/src/grace_atlas/snapshots/builder.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Build workbench snapshot from AtlasGraph + GapReport.
#   SCOPE: nodes/edges/indexes/diagnostics/diagrams/provenance write + load + inspect
#   DEPENDS: model, diagnostics, enrichment, exporters.notes, serializer, validator
#   LINKS: Phase 3A snapshot
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   build_snapshot_bundle - pure build of dict bundle
#   build_and_write_snapshot - build + write to .grace-atlas/model
#   load_snapshot - load from disk
#   validate_snapshot_dir - validate on-disk
#   inspect_entity - CLI helper for one entity
# END_MODULE_MAP

"""Build and load workbench snapshots."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.diagnostics import GapReport
from grace_atlas.exporters.notes import note_relpath
from grace_atlas.model import AtlasGraph, Edge, Node, NodeType
from grace_atlas.snapshots.schema import (
    GENERATOR_VERSION,
    HIERARCHY_RELATIONS,
    SCHEMA_VERSION,
)
from grace_atlas.snapshots.serializer import model_hash, write_snapshot_dir
from grace_atlas.snapshots.validator import SnapshotValidationError, validate_bundle, validate_model


# START_BLOCK_NODE_EDGE_MAP
def _source_state(node: Node) -> str:
    if node.properties.get("stub"):
        return "unresolved"
    return str(node.properties.get("source_state") or "declared")


def _resolution_state(edge: Edge, graph: AtlasGraph) -> str:
    if edge.source not in graph.nodes or edge.target not in graph.nodes:
        return "unresolved"
    src_n = graph.nodes[edge.source]
    tgt_n = graph.nodes[edge.target]
    if src_n.properties.get("stub") or tgt_n.properties.get("stub"):
        return "unresolved"
    return "resolved"


def _node_tags(node: Node) -> list[str]:
    tags = [f"type:{node.type}"]
    if node.status:
        tags.append(f"status:{node.status}")
    ss = _source_state(node)
    tags.append(f"source_state:{ss}")
    phase = node.properties.get("phase") or node.properties.get("current_phase")
    if phase:
        tags.append(f"phase:{phase}")
    gaps = node.properties.get("gap_types") or []
    if gaps:
        tags.append("has_gaps")
    return tags


def _node_links(node: Node, config: AtlasConfig) -> dict[str, Any]:
    rel = note_relpath(node)
    source_uri = None
    vscode_uri = None
    src_file = None
    if node.source_ref and node.source_ref.path:
        src_file = node.source_ref.path
    elif node.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
        src_file = str(node.properties.get("path") or node.name or "")
    if src_file:
        source_uri = src_file
        if config.vscode_enabled:
            abs_path = Path(src_file)
            if not abs_path.is_absolute():
                abs_path = (config.repo_root / src_file).resolve()
            line = node.source_ref.line_start if node.source_ref else None
            # vscode://file/path:line
            p = str(abs_path).replace("\\", "/")
            if not p.startswith("/"):
                # Windows drive: vscode://file/D:/path
                vscode_uri = f"vscode://file/{p}"
            else:
                vscode_uri = f"vscode://file{p}"
            if line:
                vscode_uri = f"{vscode_uri}:{line}"
    return {
        "obsidianNote": rel.replace("\\", "/"),
        "sourceUri": source_uri,
        "vscodeUri": vscode_uri,
    }


def _map_node(node: Node, config: AtlasConfig) -> dict[str, Any]:
    src = None
    if node.source_ref:
        src = {
            "file": node.source_ref.path,
            "line": node.source_ref.line_start,
            "column": None,
        }
    elif node.source:
        src = {"file": node.source, "line": None, "column": None}
    display = str(node.properties.get("display_name") or node.name or node.id)
    # Strip large wiki-link lists from properties for compact snapshot; keep scalars/lists of ids
    props: dict[str, Any] = {}
    for k, v in node.properties.items():
        if k in {"display_name"}:
            continue
        if isinstance(v, str) and v.startswith("[[") and "]]" in v:
            continue
        if isinstance(v, list) and v and isinstance(v[0], str) and str(v[0]).startswith("[["):
            # keep as-is but cap size
            props[k] = v[:50]
            continue
        props[k] = v
    return {
        "id": node.id,
        "type": node.type,
        "displayName": display,
        "description": node.description or "",
        "status": node.status or "",
        "properties": props,
        "tags": _node_tags(node),
        "source": src,
        "links": _node_links(node, config),
    }


def _map_edge(edge: Edge, graph: AtlasGraph) -> dict[str, Any]:
    return {
        "id": edge.id,
        "source": edge.source,
        "target": edge.target,
        "relation": edge.type,
        "sourceState": edge.provenance.value if hasattr(edge.provenance, "value") else str(edge.provenance),
        "resolutionState": _resolution_state(edge, graph),
        "provenance": {
            "file": edge.artifact_path or edge.relation_source or "",
            "line": edge.properties.get("line") if edge.properties else None,
            "description": edge.description or "",
        },
    }
# END_BLOCK_NODE_EDGE_MAP


# START_BLOCK_INDEXES
def _build_indexes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    diagrams: list[dict[str, Any]],
) -> dict[str, Any]:
    node_by_id: dict[str, int] = {n["id"]: i for i, n in enumerate(nodes)}
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    children: dict[str, list[str]] = defaultdict(list)
    parent: dict[str, str] = {}
    by_type: dict[str, list[str]] = defaultdict(list)
    by_status: dict[str, list[str]] = defaultdict(list)
    by_phase: dict[str, list[str]] = defaultdict(list)
    source_files: dict[str, list[str]] = defaultdict(list)
    diag_by_node: dict[str, list[int]] = defaultdict(list)
    diagrams_by_root: dict[str, list[str]] = defaultdict(list)

    for n in nodes:
        by_type[n["type"]].append(n["id"])
        st = n.get("status") or ""
        if st:
            by_status[st].append(n["id"])
        phase = (n.get("properties") or {}).get("phase") or (n.get("properties") or {}).get(
            "current_phase"
        )
        if phase:
            by_phase[str(phase)].append(n["id"])
        src = n.get("source") or {}
        if src.get("file"):
            source_files[n["id"]].append(src["file"])
        link_src = (n.get("links") or {}).get("sourceUri")
        if link_src and link_src not in source_files[n["id"]]:
            source_files[n["id"]].append(link_src)

    for e in edges:
        eid = e["id"]
        outgoing[e["source"]].append(eid)
        incoming[e["target"]].append(eid)
        rel = e["relation"]
        if rel in HIERARCHY_RELATIONS:
            # contains: parent -> child; belongs_to/planned_in: child -> parent
            if rel == "contains":
                children[e["source"]].append(e["target"])
                parent.setdefault(e["target"], e["source"])
            else:
                children[e["target"]].append(e["source"])
                parent.setdefault(e["source"], e["target"])

    for i, f in enumerate(findings):
        eid = f.get("entityId") or f.get("entity_id") or ""
        if eid:
            diag_by_node[eid].append(i)

    for d in diagrams:
        for root in d.get("rootEntityIds") or []:
            diagrams_by_root[root].append(d["id"])

    def _sorted_dict_lists(d: dict[str, list]) -> dict[str, list]:
        return {k: sorted(set(v)) for k, v in sorted(d.items())}

    return {
        "nodeById": node_by_id,
        "incomingByNode": _sorted_dict_lists(incoming),
        "outgoingByNode": _sorted_dict_lists(outgoing),
        "childrenByNode": _sorted_dict_lists(children),
        "parentByNode": dict(sorted(parent.items())),
        "diagnosticsByNode": {k: v for k, v in sorted(diag_by_node.items())},
        "nodesByType": _sorted_dict_lists(by_type),
        "nodesByStatus": _sorted_dict_lists(by_status),
        "nodesByPhase": _sorted_dict_lists(by_phase),
        "diagramsByRoot": _sorted_dict_lists(diagrams_by_root),
        "sourceFilesByNode": _sorted_dict_lists(source_files),
    }
# END_BLOCK_INDEXES


# START_BLOCK_GENERATED_DIAGRAMS
def _generated_diagrams(graph: AtlasGraph, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Catalog of generated diagram definitions (not layouts)."""
    diagrams: list[dict[str, Any]] = []
    ucs = sorted([n for n in nodes if n["type"] == NodeType.USE_CASE], key=lambda x: x["id"])
    for uc in ucs[:50]:
        diagrams.append(
            {
                "schemaVersion": "1.0.0",
                "id": f"gen:use_case_trace:{uc['id']}",
                "name": f"Use Case Trace — {uc['id']}",
                "type": "use_case_trace",
                "rootEntityIds": [uc["id"]],
                "query": {
                    "includeRelations": [
                        "related_flow",
                        "uses_use_case",
                        "implements",
                        "implemented_in",
                        "verified_by",
                        "tested_by",
                        "produces_evidence",
                    ],
                    "excludeRelations": [],
                    "includeNodeTypes": [],
                    "excludeNodeTypes": [],
                    "direction": "both",
                    "depth": 4,
                    "includeDiagnostics": True,
                },
                "layout": {
                    "algorithm": "elk-layered",
                    "direction": "RIGHT",
                    "spacing": 40,
                },
                "hiddenNodeIds": [],
                "hiddenEdgeIds": [],
                "pinnedNodeIds": [],
                "manualPositions": {},
                "collapsedGroups": [],
                "viewport": {"zoom": 1, "panX": 0, "panY": 0},
                "createdFrom": "generated",
                "readOnly": True,
            }
        )

    modules = sorted([n for n in nodes if n["type"] == NodeType.MODULE], key=lambda x: x["id"])
    for m in modules[:80]:
        diagrams.append(
            {
                "schemaVersion": "1.0.0",
                "id": f"gen:module_neighborhood:{m['id']}",
                "name": f"Module Neighborhood — {m['id']}",
                "type": "module_neighborhood",
                "rootEntityIds": [m["id"]],
                "query": {
                    "includeRelations": [
                        "depends_on",
                        "implements",
                        "implemented_in",
                        "verified_by",
                        "tested_by",
                        "has_contract",
                        "has_block",
                        "planned_in",
                    ],
                    "excludeRelations": [],
                    "includeNodeTypes": [],
                    "excludeNodeTypes": [],
                    "direction": "both",
                    "depth": 2,
                    "includeDiagnostics": True,
                },
                "layout": {
                    "algorithm": "elk-layered",
                    "direction": "RIGHT",
                    "spacing": 40,
                },
                "hiddenNodeIds": [],
                "hiddenEdgeIds": [],
                "pinnedNodeIds": [m["id"]],
                "manualPositions": {},
                "collapsedGroups": [],
                "viewport": {"zoom": 1, "panX": 0, "panY": 0},
                "createdFrom": "generated",
                "readOnly": True,
            }
        )

    # Project-level fixed diagrams
    fixed = [
        (
            "gen:current_phase",
            "Current Phase",
            "current_phase",
            [n.id for n in graph.nodes_by_type(NodeType.PHASE) if n.properties.get("current")]
            or [n.id for n in sorted(graph.nodes_by_type(NodeType.PHASE), key=lambda x: x.id)[:1]],
            ["contains", "belongs_to", "planned_in", "implements", "implemented_in", "verified_by"],
            3,
        ),
        (
            "gen:verification_gaps",
            "Verification Gaps",
            "verification",
            [n["id"] for n in nodes if "has_gaps" in (n.get("tags") or [])][:30],
            ["verified_by", "tested_by", "implements", "related_flow"],
            2,
        ),
        (
            "gen:main_user_journey",
            "Main User Journey",
            "traceability",
            [n["id"] for n in ucs[:12]],
            ["related_flow", "uses_use_case", "implements", "implemented_in", "verified_by"],
            3,
        ),
    ]
    for did, name, dtype, roots, rels, depth in fixed:
        if not roots:
            continue
        diagrams.append(
            {
                "schemaVersion": "1.0.0",
                "id": did,
                "name": name,
                "type": dtype,
                "rootEntityIds": roots,
                "query": {
                    "includeRelations": rels,
                    "excludeRelations": [],
                    "includeNodeTypes": [],
                    "excludeNodeTypes": [],
                    "direction": "both",
                    "depth": depth,
                    "includeDiagnostics": True,
                },
                "layout": {
                    "algorithm": "elk-layered",
                    "direction": "RIGHT",
                    "spacing": 40,
                },
                "hiddenNodeIds": [],
                "hiddenEdgeIds": [],
                "pinnedNodeIds": [],
                "manualPositions": {},
                "collapsedGroups": [],
                "viewport": {"zoom": 1, "panX": 0, "panY": 0},
                "createdFrom": "generated",
                "readOnly": True,
            }
        )
    diagrams.sort(key=lambda d: d["id"])
    return diagrams
# END_BLOCK_GENERATED_DIAGRAMS


def _map_finding(f: Any, index: int) -> dict[str, Any]:
    d = f.as_dict() if hasattr(f, "as_dict") else {
        "code": f.code,
        "severity": f.severity,
        "message": f.message,
        "entity_id": f.entity_id,
        "provenance": f.provenance,
        "source_path": f.source_path,
        "source_line": f.source_line,
        "related": list(f.related or []),
        "details": dict(f.details or {}),
    }
    return {
        "id": f"diag:{index}:{d.get('code', '')}:{d.get('entity_id', '')}",
        "code": d.get("code", ""),
        "severity": d.get("severity", "info"),
        "message": d.get("message", ""),
        "entityId": d.get("entity_id", ""),
        "sourceState": d.get("provenance", "declared"),
        "source": {
            "file": d.get("source_path") or "",
            "line": d.get("source_line"),
        },
        "related": d.get("related") or [],
        "details": d.get("details") or {},
        "suggestedAction": (d.get("details") or {}).get("suggested_action")
        or (d.get("details") or {}).get("reason")
        or "",
        "phaseRelevance": (d.get("details") or {}).get("phase_relevance"),
        "userJourneyRelevance": (d.get("details") or {}).get("user_journey_relevance"),
        "actionable": d.get("severity") in {"error", "warning"},
    }


def model_dir_for(config: AtlasConfig) -> Path:
    return (config.repo_root / ".grace-atlas" / "model").resolve()


def build_snapshot_bundle(
    graph: AtlasGraph,
    report: GapReport,
    config: AtlasConfig,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Pure build of snapshot dicts (no I/O)."""
    # Ensure stable order
    nodes_src = sorted(graph.nodes.values(), key=lambda n: n.id)
    edges_src = sorted(graph.edges, key=lambda e: e.id)

    nodes = [_map_node(n, config) for n in nodes_src]
    edges = [_map_edge(e, graph) for e in edges_src]
    findings = [_map_finding(f, i) for i, f in enumerate(report.findings)]
    diagrams = _generated_diagrams(graph, nodes)

    model = {
        "schemaVersion": SCHEMA_VERSION,
        "nodes": nodes,
        "edges": edges,
    }
    diagnostics = {
        "schemaVersion": SCHEMA_VERSION,
        "summary": dict(report.summary or {}),
        "findings": findings,
    }
    indexes = _build_indexes(nodes, edges, findings, diagrams)
    diagrams_generated = {
        "schemaVersion": SCHEMA_VERSION,
        "diagrams": diagrams,
    }
    mhash = model_hash(model, diagnostics)
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    project_id = config.project_name.lower().replace(" ", "-")
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generatorVersion": GENERATOR_VERSION,
        "project": {
            "id": project_id,
            "name": config.project_name,
            "root": str(config.repo_root.resolve()),
        },
        "generatedAt": ts,
        "modelHash": mhash,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "diagnosticCount": len(findings),
        "files": {
            "model": "model.json",
            "diagnostics": "diagnostics.json",
            "indexes": "indexes.json",
            "diagramsGenerated": "diagrams.generated.json",
            "provenance": "provenance.json",
            "schema": "schemas/workbench-model.schema.json",
        },
    }
    provenance = {
        "schemaVersion": SCHEMA_VERSION,
        "modelHash": mhash,
        "generatorVersion": GENERATOR_VERSION,
        "graphMeta": dict(graph.meta or {}),
        "artifactPaths": {
            k: str(v) if v is not None else None
            for k, v in (graph.meta.get("artifacts") or {}).items()
        }
        if isinstance(graph.meta.get("artifacts"), dict)
        else {},
        "buildOptions": {
            "includeSource": True,
        },
    }
    return {
        "manifest": manifest,
        "model": model,
        "diagnostics": diagnostics,
        "indexes": indexes,
        "diagrams_generated": diagrams_generated,
        "provenance": provenance,
    }


def build_and_write_snapshot(
    graph: AtlasGraph,
    report: GapReport,
    config: AtlasConfig,
    *,
    model_dir: Path | None = None,
) -> dict[str, Any]:
    """Build snapshot and write under .grace-atlas/model/. Returns manifest + paths."""
    bundle = build_snapshot_bundle(graph, report, config)
    out_dir = model_dir or model_dir_for(config)
    written = write_snapshot_dir(
        out_dir,
        manifest=bundle["manifest"],
        model=bundle["model"],
        diagnostics=bundle["diagnostics"],
        indexes=bundle["indexes"],
        diagrams_generated=bundle["diagrams_generated"],
        provenance=bundle["provenance"],
    )
    return {
        "model_dir": str(out_dir),
        "manifest": bundle["manifest"],
        "files": written,
        "nodeCount": bundle["manifest"]["nodeCount"],
        "edgeCount": bundle["manifest"]["edgeCount"],
        "diagnosticCount": bundle["manifest"]["diagnosticCount"],
        "modelHash": bundle["manifest"]["modelHash"],
    }


def load_snapshot(model_dir: Path) -> dict[str, Any]:
    """Load snapshot files from disk. Raises SnapshotValidationError if broken."""
    model_dir = Path(model_dir)
    paths = {
        "manifest": model_dir / "manifest.json",
        "model": model_dir / "model.json",
        "diagnostics": model_dir / "diagnostics.json",
        "indexes": model_dir / "indexes.json",
        "diagrams_generated": model_dir / "diagrams.generated.json",
        "provenance": model_dir / "provenance.json",
    }
    missing = [k for k, p in paths.items() if k in {"manifest", "model"} and not p.is_file()]
    if missing:
        raise SnapshotValidationError(
            "MISSING",
            f"Snapshot incomplete under {model_dir}: missing {', '.join(missing)}",
        )

    def _read(p: Path) -> Any:
        if not p.is_file():
            return None
        # Retry once for atomic replace race
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return json.loads(p.read_text(encoding="utf-8"))

    data = {k: _read(p) for k, p in paths.items()}
    validate_bundle(data["manifest"], data["model"], data["diagnostics"], data["indexes"])
    return data


def validate_snapshot_dir(model_dir: Path) -> dict[str, Any]:
    data = load_snapshot(model_dir)
    errors = validate_model(data["model"])
    if errors:
        raise SnapshotValidationError("INVALID_MODEL", "validation failed", details=errors)
    m = data["manifest"]
    return {
        "ok": True,
        "model_dir": str(model_dir),
        "schemaVersion": m.get("schemaVersion"),
        "modelHash": m.get("modelHash"),
        "nodeCount": m.get("nodeCount"),
        "edgeCount": m.get("edgeCount"),
        "diagnosticCount": m.get("diagnosticCount"),
    }


def inspect_entity(model_dir: Path, entity_id: str) -> dict[str, Any]:
    data = load_snapshot(model_dir)
    model = data["model"]
    indexes = data["indexes"] or {}
    nodes = model["nodes"]
    edges = model["edges"]
    node_by_id = indexes.get("nodeById") or {n["id"]: i for i, n in enumerate(nodes)}
    idx = node_by_id.get(entity_id)
    if idx is None:
        # case-insensitive fallback
        for n in nodes:
            if n["id"].upper() == entity_id.upper():
                entity_id = n["id"]
                idx = node_by_id[entity_id]
                break
    if idx is None:
        raise KeyError(entity_id)
    node = nodes[idx]
    out_ids = indexes.get("outgoingByNode", {}).get(entity_id, [])
    in_ids = indexes.get("incomingByNode", {}).get(entity_id, [])
    edge_by_id = {e["id"]: e for e in edges}
    outgoing = [edge_by_id[i] for i in out_ids if i in edge_by_id]
    incoming = [edge_by_id[i] for i in in_ids if i in edge_by_id]
    diag_idx = indexes.get("diagnosticsByNode", {}).get(entity_id, [])
    findings = data["diagnostics"]["findings"] if data.get("diagnostics") else []
    node_findings = [findings[i] for i in diag_idx if i < len(findings)]
    return {
        "node": node,
        "outgoing": outgoing,
        "incoming": incoming,
        "findings": node_findings,
        "parent": indexes.get("parentByNode", {}).get(entity_id),
        "children": indexes.get("childrenByNode", {}).get(entity_id, []),
        "diagrams": indexes.get("diagramsByRoot", {}).get(entity_id, []),
        "modelHash": data["manifest"].get("modelHash"),
    }

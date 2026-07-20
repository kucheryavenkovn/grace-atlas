# FILE: tools/grace_atlas/src/grace_atlas/roundtrip/drift.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Detect drift between GRACE model and source fingerprints.
#   SCOPE: missing in model/code, changed contracts, unmapped, stale evidence, suggestions
#   DEPENDS: scanner fingerprints, graph, diagnostics
#   LINKS: Phase 3D
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Drift analysis."""

from __future__ import annotations

from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.enrichment import enrich_graph
from grace_atlas.graph import build_graph
from grace_atlas.model import EdgeType, NodeType
from grace_atlas.roundtrip.fingerprints import load_store
from grace_atlas.roundtrip.scanner import scan_project


def compute_drift(config: AtlasConfig, *, rescan: bool = True) -> dict[str, Any]:
    if rescan:
        scan_project(config, changed_only=False)
    store = load_store(config)
    files_map: dict[str, Any] = store.get("files") or {}

    graph, _ = build_graph(config, include_source=True)
    report = build_gap_report(graph)
    enrich_graph(graph, report)

    items: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []

    # Index model source files
    model_files: dict[str, str] = {}
    for n in graph.nodes_by_type(NodeType.SOURCE_FILE) + graph.nodes_by_type(NodeType.TEST_FILE):
        p = str(n.properties.get("path") or n.name or "").replace("\\", "/")
        if p:
            model_files[p] = n.id

    # Missing in model: fingerprint exists, no SourceFile node
    for rel, fp in sorted(files_map.items()):
        if rel.startswith("tools/grace_atlas"):
            continue  # atlas itself optional
        if rel not in model_files and rel.startswith(("src/", "tests/")):
            items.append(
                {
                    "category": "missing_in_model",
                    "confidence": 0.9,
                    "summary": f"Source file not in model: {rel}",
                    "path": rel,
                    "sourceState": "inferred",
                    "reason": "File present on disk with fingerprint but no SourceFile/TestFile node",
                }
            )
            suggestions.append(
                {
                    "kind": "add_source_mapping",
                    "confidence": 0.7,
                    "reason": f"Map {rel} into GRACE source markup / graph",
                    "sourceState": "inferred",
                    "patchHint": {
                        "operation": "add_edge",
                        "note": "May require source markup MODULE_CONTRACT; not auto-applied",
                    },
                }
            )

    # Missing in code: model references path that has no fingerprint
    for path, nid in sorted(model_files.items()):
        if path not in files_map:
            # file might be outside include patterns
            abs_p = config.repo_root / path
            if not abs_p.is_file():
                items.append(
                    {
                        "category": "missing_in_code",
                        "confidence": 1.0,
                        "summary": f"Model file missing on disk: {path}",
                        "entityId": nid,
                        "path": path,
                        "sourceState": "declared",
                        "reason": "SourceFile node path does not exist",
                    }
                )
                suggestions.append(
                    {
                        "kind": "remove_broken_link",
                        "confidence": 0.85,
                        "reason": f"Remove or retarget broken file node {nid}",
                        "sourceState": "inferred",
                        "entityId": nid,
                    }
                )

    # Changed contract: semantic hash change for files with contracts in model
    last = store.get("lastScan") or {}
    for rel in last.get("modified") or []:
        fp = files_map.get(rel) or {}
        items.append(
            {
                "category": "unverified_change",
                "confidence": 1.0,
                "summary": f"Source changed since last scan: {rel}",
                "path": rel,
                "contentHash": fp.get("contentHash"),
                "sourceState": "declared",
                "reason": "contentHash differs from previous fingerprint",
            }
        )
        # requirement impact via module links
        for n in graph.nodes.values():
            if n.type == NodeType.MODULE:
                impl = n.properties.get("implemented_in") or []
                # also edges
                pass
        nid = model_files.get(rel)
        if nid:
            # modules that implement this file
            for e in graph.edges:
                if e.type == EdgeType.IMPLEMENTED_IN and e.target == nid:
                    items.append(
                        {
                            "category": "requirement_impact",
                            "confidence": 0.8,
                            "summary": f"Module {e.source} may be impacted by change in {rel}",
                            "entityId": e.source,
                            "path": rel,
                            "sourceState": "inferred",
                            "reason": f"{rel} changed → implemented_in {e.source}",
                        }
                    )

    # Contract markers drift
    for rel, fp in files_map.items():
        nid = model_files.get(rel)
        if not nid:
            continue
        for e in graph.edges:
            if e.type == EdgeType.HAS_CONTRACT and e.source == nid:
                # contract node should appear in parsed contracts loosely
                contract_node = graph.nodes.get(e.target)
                if contract_node and contract_node.name:
                    markers = fp.get("parsedContracts") or []
                    # only flag if we parse markers and none match name
                    if markers and contract_node.name not in markers and contract_node.id not in markers:
                        items.append(
                            {
                                "category": "changed_contract",
                                "confidence": 0.55,
                                "summary": f"Contract {e.target} not found in markers of {rel}",
                                "entityId": e.target,
                                "path": rel,
                                "sourceState": "inferred",
                                "reason": "semantic marker mismatch",
                                "candidates": markers[:10],
                            }
                        )

    # Stale evidence: evidence node older than related file hash change is approximate
    for n in graph.nodes_by_type(NodeType.EVIDENCE):
        related_files: list[str] = []
        for e in graph.edges:
            if e.source == n.id or e.target == n.id:
                other = e.target if e.source == n.id else e.source
                on = graph.nodes.get(other)
                if on and on.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
                    p = str(on.properties.get("path") or on.name or "")
                    if p:
                        related_files.append(p.replace("\\", "/"))
        for p in related_files:
            if p in (last.get("modified") or []):
                items.append(
                    {
                        "category": "evidence_stale",
                        "confidence": 0.9,
                        "summary": f"Evidence {n.id} may be stale due to change in {p}",
                        "entityId": n.id,
                        "path": p,
                        "sourceState": "inferred",
                        "reason": "Related source file content changed after evidence linkage",
                    }
                )
                suggestions.append(
                    {
                        "kind": "mark_evidence_stale",
                        "confidence": 0.9,
                        "reason": f"Mark {n.id} stale",
                        "sourceState": "inferred",
                        "entityId": n.id,
                    }
                )

    # Unmapped diagnostics from gap report
    for f in report.findings:
        if f.code in {"UNMAPPED_FILE", "STUB_MODULE", "BROKEN_REFERENCE", "ORPHAN_REQUIREMENT"}:
            items.append(
                {
                    "category": {
                        "UNMAPPED_FILE": "missing_in_model",
                        "STUB_MODULE": "missing_in_code",
                        "BROKEN_REFERENCE": "missing_in_code",
                        "ORPHAN_REQUIREMENT": "requirement_impact",
                    }.get(f.code, "missing_in_model"),
                    "confidence": 1.0 if f.severity == "error" else 0.75,
                    "summary": f"{f.code}: {f.message}",
                    "entityId": f.entity_id,
                    "sourceState": f.provenance,
                    "reason": "from diagnostics",
                }
            )

    # Sort: higher confidence first, stable category
    items.sort(key=lambda x: (-float(x.get("confidence") or 0), x.get("category") or "", x.get("summary") or ""))

    return {
        "schemaVersion": "1.0.0",
        "itemCount": len(items),
        "items": items,
        "suggestions": suggestions,
        "fingerprintFileCount": len(files_map),
        "note": "Inferred items never become declared without explicit GracePatch confirmation",
    }

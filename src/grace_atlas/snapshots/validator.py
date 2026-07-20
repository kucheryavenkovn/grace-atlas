# FILE: tools/grace_atlas/src/grace_atlas/snapshots/validator.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Validate workbench snapshot structure and referential integrity.
#   SCOPE: schema version, required fields, edge endpoints, index consistency
#   DEPENDS: schema
#   LINKS: Phase 3A snapshot
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   SnapshotValidationError - structured validation failure
#   validate_model - validate in-memory model dict
#   validate_bundle - validate full snapshot bundle
# END_MODULE_MAP

"""Snapshot validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grace_atlas.snapshots.schema import SCHEMA_VERSION, is_compatible_schema


@dataclass
class SnapshotValidationError(Exception):
    code: str
    message: str
    details: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        extra = ""
        if self.details:
            extra = "\n  - " + "\n  - ".join(self.details[:20])
            if len(self.details) > 20:
                extra += f"\n  ... and {len(self.details) - 20} more"
        return f"[{self.code}] {self.message}{extra}"


def validate_model(model: dict[str, Any], *, check_refs: bool = True) -> list[str]:
    """Return list of error strings (empty = ok)."""
    errors: list[str] = []
    if not isinstance(model, dict):
        return ["model is not an object"]
    ver = model.get("schemaVersion")
    if not ver:
        errors.append("missing schemaVersion")
    elif not is_compatible_schema(str(ver)):
        errors.append(
            f"incompatible schemaVersion {ver!r}; supported major compatible with {SCHEMA_VERSION}"
        )
    nodes = model.get("nodes")
    edges = model.get("edges")
    if not isinstance(nodes, list):
        errors.append("nodes must be an array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        edges = []

    ids: set[str] = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            errors.append(f"nodes[{i}] is not an object")
            continue
        nid = n.get("id")
        if not nid:
            errors.append(f"nodes[{i}] missing id")
            continue
        if nid in ids:
            errors.append(f"duplicate node id: {nid}")
        ids.add(str(nid))
        if not n.get("type"):
            errors.append(f"node {nid} missing type")
        if "displayName" not in n:
            errors.append(f"node {nid} missing displayName")

    edge_ids: set[str] = set()
    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            errors.append(f"edges[{i}] is not an object")
            continue
        eid = e.get("id") or f"edge-{i}"
        if eid in edge_ids:
            errors.append(f"duplicate edge id: {eid}")
        edge_ids.add(str(eid))
        for key in ("source", "target", "relation"):
            if not e.get(key):
                errors.append(f"edge {eid} missing {key}")
        if check_refs:
            src, tgt = e.get("source"), e.get("target")
            if src and src not in ids:
                errors.append(f"edge {eid} source missing: {src}")
            if tgt and tgt not in ids:
                errors.append(f"edge {eid} target missing: {tgt}")
    return errors


def validate_bundle(
    manifest: dict[str, Any] | None,
    model: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None = None,
    indexes: dict[str, Any] | None = None,
) -> None:
    """Raise SnapshotValidationError if invalid."""
    if not manifest:
        raise SnapshotValidationError("MISSING_MANIFEST", "manifest.json missing or empty")
    if not model:
        raise SnapshotValidationError("MISSING_MODEL", "model.json missing or empty")

    mver = str(manifest.get("schemaVersion") or "")
    if not is_compatible_schema(mver):
        raise SnapshotValidationError(
            "INCOMPATIBLE_SCHEMA",
            f"Snapshot schemaVersion {mver!r} is not compatible with plugin/core "
            f"(supported: {SCHEMA_VERSION}). Rebuild with a matching grace-atlas version.",
            details=[f"manifest.schemaVersion={mver}"],
        )

    errors = validate_model(model)
    if errors:
        raise SnapshotValidationError("INVALID_MODEL", "model.json failed validation", details=errors)

    if diagnostics is not None and not isinstance(diagnostics.get("findings"), list):
        raise SnapshotValidationError("INVALID_DIAGNOSTICS", "diagnostics.findings must be an array")

    if indexes is not None and not isinstance(indexes.get("nodeById"), dict):
        raise SnapshotValidationError("INVALID_INDEXES", "indexes.nodeById must be an object")

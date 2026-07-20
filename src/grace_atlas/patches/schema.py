# FILE: tools/grace_atlas/src/grace_atlas/patches/schema.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: GracePatch schema and parse/validate helpers.
#   SCOPE: operations whitelist, preconditions, load from JSON
#   DEPENDS: dataclasses, json
#   LINKS: Phase 3C
#   ROLE: TYPES
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""GracePatch data model."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PATCH_SCHEMA_VERSION = "1.0"
SUPPORTED_OPERATIONS = frozenset(
    {
        "add_edge",
        "remove_edge",
        "update_property",
        "create_verification_link",
        "assign_to_phase",
        "update_status",
        "add_evidence_reference",
    }
)

# Relations that may be written into knowledge-graph CrossLink style edges
WRITABLE_RELATIONS = frozenset(
    {
        "implements",
        "implemented_in",
        "depends_on",
        "verified_by",
        "tested_by",
        "related_flow",
        "cross_link",
        "links_to",
        "refers_to",
        "planned_in",
        "produces_evidence",
    }
)


@dataclass
class PatchOperation:
    operation: str
    source: str | None = None
    target: str | None = None
    relation: str | None = None
    entity_id: str | None = None
    property: str | None = None
    value: Any = None
    expected_old_value: Any = None
    expected_source_state: str | None = None
    reason: str = ""
    preconditions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PatchOperation:
        return cls(
            operation=str(d.get("operation") or ""),
            source=d.get("source"),
            target=d.get("target"),
            relation=d.get("relation"),
            entity_id=d.get("entityId") or d.get("entity_id"),
            property=d.get("property"),
            value=d.get("value"),
            expected_old_value=d.get("expectedOldValue", d.get("expected_old_value")),
            expected_source_state=d.get("expectedSourceState", d.get("expected_source_state")),
            reason=str(d.get("reason") or ""),
            preconditions=dict(d.get("preconditions") or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != "" and v != {}}


@dataclass
class GracePatch:
    schema_version: str
    patch_id: str
    created_at: str
    project_hash: str | None
    operations: list[PatchOperation]
    author: dict[str, Any] = field(default_factory=lambda: {"type": "human", "name": None})
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GracePatch:
        ops = [PatchOperation.from_dict(o) for o in (d.get("operations") or [])]
        return cls(
            schema_version=str(d.get("schemaVersion") or d.get("schema_version") or PATCH_SCHEMA_VERSION),
            patch_id=str(d.get("patchId") or d.get("patch_id") or str(uuid.uuid4())),
            created_at=str(
                d.get("createdAt")
                or d.get("created_at")
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ),
            project_hash=d.get("projectHash") or d.get("project_hash"),
            operations=ops,
            author=dict(d.get("author") or {"type": "human", "name": None}),
            meta=dict(d.get("meta") or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "patchId": self.patch_id,
            "createdAt": self.created_at,
            "projectHash": self.project_hash,
            "operations": [o.as_dict() for o in self.operations],
            "author": self.author,
            "meta": self.meta,
        }


def validate_patch_schema(patch: GracePatch) -> list[str]:
    errors: list[str] = []
    if patch.schema_version.split(".")[0] != PATCH_SCHEMA_VERSION.split(".")[0]:
        errors.append(f"unsupported patch schemaVersion {patch.schema_version}")
    if not patch.operations:
        errors.append("operations must be non-empty")
    for i, op in enumerate(patch.operations):
        if op.operation not in SUPPORTED_OPERATIONS:
            errors.append(f"operations[{i}]: unsupported operation {op.operation!r}")
            continue
        if op.operation in {"add_edge", "remove_edge", "create_verification_link"}:
            if not op.source or not op.target:
                errors.append(f"operations[{i}]: source and target required")
            rel = op.relation or ("verified_by" if op.operation == "create_verification_link" else None)
            if not rel:
                errors.append(f"operations[{i}]: relation required")
            elif rel not in WRITABLE_RELATIONS:
                errors.append(f"operations[{i}]: relation {rel!r} not writable")
        if op.operation == "update_property":
            if not op.entity_id or not op.property:
                errors.append(f"operations[{i}]: entity_id and property required")
        if op.operation == "update_status":
            if not op.entity_id or op.value is None:
                errors.append(f"operations[{i}]: entity_id and value required for update_status")
        if op.operation == "assign_to_phase":
            if not op.entity_id or not op.target:
                errors.append(f"operations[{i}]: entity_id and target phase required")
        if op.operation == "add_evidence_reference":
            if not op.source or not op.target:
                errors.append(f"operations[{i}]: source and target required for evidence ref")
    return errors


def load_patch(path: Path) -> GracePatch:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return GracePatch.from_dict(data)


def new_patch(
    operations: list[dict[str, Any]],
    *,
    project_hash: str | None = None,
    author: dict[str, Any] | None = None,
) -> GracePatch:
    return GracePatch.from_dict(
        {
            "schemaVersion": PATCH_SCHEMA_VERSION,
            "patchId": str(uuid.uuid4()),
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "projectHash": project_hash,
            "operations": operations,
            "author": author or {"type": "human", "name": None},
        }
    )

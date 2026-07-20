# FILE: tools/grace_atlas/src/grace_atlas/snapshots/schema.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: JSON Schema and constants for workbench snapshot format.
#   SCOPE: schema versioning, structural field definitions
#   DEPENDS: none
#   LINKS: Phase 3A snapshot
#   ROLE: TYPES
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   SCHEMA_VERSION - major.minor.patch of snapshot format
#   WORKBENCH_MODEL_SCHEMA - JSON Schema dict
# END_MODULE_MAP

"""Workbench snapshot JSON Schema."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "0.4.0"

# Parent/child style relations used for tree indexes
HIERARCHY_RELATIONS = frozenset(
    {
        "contains",
        "belongs_to",
        "planned_in",
    }
)

WORKBENCH_MODEL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://grace-atlas.local/schemas/workbench-model.schema.json",
    "title": "GRACE Workbench Snapshot",
    "type": "object",
    "required": ["schemaVersion", "nodes", "edges"],
    "additionalProperties": True,
    "properties": {
        "schemaVersion": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "type", "displayName"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "type": {"type": "string"},
                    "displayName": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "properties": {"type": "object"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "source": {
                        "type": ["object", "null"],
                        "properties": {
                            "file": {"type": "string"},
                            "line": {"type": ["integer", "null"]},
                            "column": {"type": ["integer", "null"]},
                        },
                    },
                    "links": {"type": "object"},
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "source", "target", "relation"],
                "properties": {
                    "id": {"type": "string"},
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "relation": {"type": "string"},
                    "sourceState": {"type": "string"},
                    "resolutionState": {"type": "string"},
                    "provenance": {"type": "object"},
                },
            },
        },
    },
}


def is_compatible_schema(version: str, *, supported: str = SCHEMA_VERSION) -> bool:
    """Compatible if major matches and minor <= supported minor."""
    try:
        maj, minor, _ = (int(x) for x in version.split("."))
        s_maj, s_minor, _ = (int(x) for x in supported.split("."))
    except (ValueError, AttributeError):
        return False
    if maj != s_maj:
        return False
    return minor <= s_minor

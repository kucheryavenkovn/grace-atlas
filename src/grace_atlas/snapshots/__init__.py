# FILE: tools/grace_atlas/src/grace_atlas/snapshots/__init__.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Workbench snapshot package — Obsidian-independent normalized model export.
#   SCOPE: schema, builder, serializer, validator, generated diagrams
#   DEPENDS: grace_atlas.model, diagnostics, enrichment
#   LINKS: M-SNAPSHOT, Phase 3A
#   ROLE: BARREL
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   SCHEMA_VERSION - snapshot schema version
#   GENERATOR_VERSION - atlas generator version for snapshots
#   build_and_write_snapshot - full pipeline
#   validate_snapshot_dir - validate on-disk snapshot
#   inspect_entity - inspect one entity from snapshot
#   load_snapshot - load snapshot dicts from disk
#   model_dir_for - resolve .grace-atlas/model path
# END_MODULE_MAP

"""Workbench snapshot public API."""

from grace_atlas.snapshots.builder import (
    build_and_write_snapshot,
    build_snapshot_bundle,
    inspect_entity,
    load_snapshot,
    model_dir_for,
    validate_snapshot_dir,
)
from grace_atlas.snapshots.schema import GENERATOR_VERSION, SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "GENERATOR_VERSION",
    "build_and_write_snapshot",
    "build_snapshot_bundle",
    "validate_snapshot_dir",
    "inspect_entity",
    "load_snapshot",
    "model_dir_for",
]

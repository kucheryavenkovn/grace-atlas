# FILE: tools/grace_atlas/src/grace_atlas/snapshots/serializer.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Deterministic JSON serialization and atomic writes for snapshots.
#   SCOPE: stable sort, model hash, atomic replace, schema file write
#   DEPENDS: json, hashlib, pathlib
#   LINKS: Phase 3A snapshot
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   dumps_deterministic - stable JSON string
#   model_hash - content hash excluding volatile timestamps
#   atomic_write_json - write via temp + replace
#   write_snapshot_dir - write full model directory
# END_MODULE_MAP

"""Deterministic serialization helpers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from grace_atlas.snapshots.schema import WORKBENCH_MODEL_SCHEMA


def dumps_deterministic(obj: Any) -> str:
    """Serialize with sorted keys and stable separators (no trailing newline variance)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"


def model_hash(model: dict[str, Any], diagnostics: dict[str, Any] | None = None) -> str:
    """
    Hash of model content + diagnostics content.
    Excludes generatedAt and other volatile fields so rebuilds stay stable when data unchanged.
    """
    payload = {
        "schemaVersion": model.get("schemaVersion"),
        "nodes": model.get("nodes"),
        "edges": model.get("edges"),
    }
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics.get("findings")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically (temp in same dir + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=path.suffix, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, dumps_deterministic(obj))


def write_snapshot_dir(
    model_dir: Path,
    *,
    manifest: dict[str, Any],
    model: dict[str, Any],
    diagnostics: dict[str, Any],
    indexes: dict[str, Any],
    diagrams_generated: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, str]:
    """Write all snapshot files atomically. Returns relative paths written."""
    model_dir.mkdir(parents=True, exist_ok=True)
    schemas_dir = model_dir / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "manifest": model_dir / "manifest.json",
        "model": model_dir / "model.json",
        "diagnostics": model_dir / "diagnostics.json",
        "indexes": model_dir / "indexes.json",
        "diagrams_generated": model_dir / "diagrams.generated.json",
        "provenance": model_dir / "provenance.json",
        "schema": schemas_dir / "workbench-model.schema.json",
    }

    atomic_write_json(files["model"], model)
    atomic_write_json(files["diagnostics"], diagnostics)
    atomic_write_json(files["indexes"], indexes)
    atomic_write_json(files["diagrams_generated"], diagrams_generated)
    atomic_write_json(files["provenance"], provenance)
    atomic_write_json(files["schema"], WORKBENCH_MODEL_SCHEMA)
    # Manifest last so readers that watch it see complete payloads
    atomic_write_json(files["manifest"], manifest)

    return {k: str(v.relative_to(model_dir)).replace("\\", "/") for k, v in files.items()}

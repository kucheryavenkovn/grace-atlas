# FILE: tools/grace_atlas/src/grace_atlas/diagrams/catalog.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Persist user DiagramDefinition JSON files without touching generated diagrams.
#   SCOPE: CRUD under .grace-atlas/user/diagrams/*.json
#   DEPENDS: config paths
#   LINKS: Phase 3B
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""User diagram persistence."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.snapshots.serializer import atomic_write_json

DIAGRAM_SCHEMA_VERSION = "1.0.0"


def user_diagrams_dir(config: AtlasConfig) -> Path:
    return (config.repo_root / ".grace-atlas" / "user" / "diagrams").resolve()


def _safe_id(diagram_id: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", diagram_id)
    return s[:120] or "diagram"


def list_user_diagrams(config: AtlasConfig) -> list[dict[str, Any]]:
    d = user_diagrams_dir(config)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return out


def load_user_diagram(config: AtlasConfig, diagram_id: str) -> dict[str, Any] | None:
    path = user_diagrams_dir(config) / f"{_safe_id(diagram_id)}.json"
    if not path.is_file():
        # search by id field
        for d in list_user_diagrams(config):
            if d.get("id") == diagram_id:
                return d
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_user_diagram(config: AtlasConfig, diagram: dict[str, Any]) -> Path:
    d = user_diagrams_dir(config)
    d.mkdir(parents=True, exist_ok=True)
    if not diagram.get("id"):
        diagram["id"] = f"user:{uuid.uuid4()}"
    diagram.setdefault("schemaVersion", DIAGRAM_SCHEMA_VERSION)
    diagram.setdefault("createdFrom", "user")
    diagram.setdefault("readOnly", False)
    diagram["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = d / f"{_safe_id(diagram['id'])}.json"
    atomic_write_json(path, diagram)
    return path


def delete_user_diagram(config: AtlasConfig, diagram_id: str) -> bool:
    path = user_diagrams_dir(config) / f"{_safe_id(diagram_id)}.json"
    if path.is_file():
        path.unlink()
        return True
    # try match id field
    for p in user_diagrams_dir(config).glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("id") == diagram_id:
            p.unlink()
            return True
    return False


def mark_unresolved_nodes(diagram: dict[str, Any], existing_ids: set[str]) -> dict[str, Any]:
    """Annotate diagram with unresolved root/pinned/hidden nodes (tombstones)."""
    unresolved: list[str] = []
    for key in ("rootEntityIds", "pinnedNodeIds", "hiddenNodeIds"):
        for nid in diagram.get(key) or []:
            if nid not in existing_ids:
                unresolved.append(nid)
    for nid in (diagram.get("manualPositions") or {}):
        if nid not in existing_ids:
            unresolved.append(nid)
    diagram["unresolvedNodeIds"] = sorted(set(unresolved))
    return diagram

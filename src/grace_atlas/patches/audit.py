# FILE: tools/grace_atlas/src/grace_atlas/patches/audit.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Append-only audit log for GracePatch outcomes.
#   SCOPE: jsonl under .grace-atlas/user/audit/
#   DEPENDS: json, pathlib
#   LINKS: Phase 3C
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Patch audit log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grace_atlas.config import AtlasConfig


def audit_path(config: AtlasConfig) -> Path:
    return (config.repo_root / ".grace-atlas" / "user" / "audit" / "patch-history.jsonl").resolve()


def append_audit(config: AtlasConfig, entry: dict[str, Any]) -> Path:
    path = audit_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **entry,
    }
    # Never store full private file contents
    for key in ("diff", "fullDiff", "fileContents"):
        if key in record and isinstance(record[key], str) and len(record[key]) > 4000:
            record[key] = record[key][:4000] + "\n...[truncated]"
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return path


def read_audit(config: AtlasConfig, *, limit: int = 200) -> list[dict[str, Any]]:
    path = audit_path(config)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def find_audit_entry(config: AtlasConfig, patch_id: str) -> dict[str, Any] | None:
    for entry in reversed(read_audit(config, limit=5000)):
        if entry.get("patchId") == patch_id or entry.get("patch_id") == patch_id:
            return entry
    return None

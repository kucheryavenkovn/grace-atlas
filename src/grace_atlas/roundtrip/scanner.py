# FILE: tools/grace_atlas/src/grace_atlas/roundtrip/scanner.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Hash-based full or incremental source fingerprint scan.
#   SCOPE: walk includes/excludes from config, update store, report changes
#   DEPENDS: fingerprints, config
#   LINKS: Phase 3D
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Incremental scanner."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.roundtrip.fingerprints import (
    fingerprint_file,
    load_store,
    save_store,
    store_path,
)


def _iter_source_files(config: AtlasConfig) -> list[Path]:
    root = config.repo_root
    includes = config.source_include or ["src/**/*.py", "tests/**/*.py"]
    excludes = config.source_exclude or []
    found: set[Path] = set()
    for pattern in includes:
        # pathlib-ish glob: ** supported
        for p in root.glob(pattern):
            if p.is_file():
                found.add(p.resolve())
    out: list[Path] = []
    for p in sorted(found):
        rel = str(p.relative_to(root)).replace("\\", "/")
        if any(fnmatch.fnmatch(rel, ex) or fnmatch.fnmatch(rel, ex.rstrip("/")) for ex in excludes):
            continue
        # also skip path parts
        if any(part in {".git", ".venv", "__pycache__", ".grace-atlas"} for part in p.parts):
            continue
        out.append(p)
    return out


def scan_project(config: AtlasConfig, *, changed_only: bool = False) -> dict[str, Any]:
    store = load_store(config)
    files_map: dict[str, Any] = dict(store.get("files") or {})
    scanned = 0
    changed = 0
    skipped = 0
    added: list[str] = []
    removed: list[str] = []
    modified: list[str] = []
    current_paths: set[str] = set()

    for path in _iter_source_files(config):
        rel = str(path.relative_to(config.repo_root)).replace("\\", "/")
        current_paths.add(rel)
        prev = files_map.get(rel)
        if changed_only and prev:
            # quick size+mtime gate then hash
            try:
                st = path.stat()
                if prev.get("size") == st.st_size:
                    # still re-hash content for correctness (required: hash-based)
                    fp = fingerprint_file(path, rel=rel)
                    scanned += 1
                    if fp["contentHash"] == prev.get("contentHash"):
                        skipped += 1
                        # refresh lastScanned only
                        prev["lastScanned"] = fp["lastScanned"]
                        files_map[rel] = prev
                        continue
                    files_map[rel] = fp
                    changed += 1
                    modified.append(rel)
                    continue
            except OSError:
                pass
        fp = fingerprint_file(path, rel=rel)
        scanned += 1
        if prev is None:
            added.append(rel)
            changed += 1
        elif prev.get("contentHash") != fp["contentHash"]:
            modified.append(rel)
            changed += 1
        else:
            skipped += 1
        files_map[rel] = fp

    # removals
    for old in list(files_map.keys()):
        if old not in current_paths:
            removed.append(old)
            del files_map[old]
            changed += 1

    store["files"] = files_map
    store["schemaVersion"] = "1.0.0"
    store["lastScan"] = {
        "scanned": scanned,
        "changed": changed,
        "skipped": skipped,
        "added": added,
        "removed": removed,
        "modified": modified,
        "changedOnly": changed_only,
    }
    path = save_store(config, store)
    return {
        "scanned": scanned,
        "changed": changed,
        "skipped": skipped,
        "added": added,
        "removed": removed,
        "modified": modified,
        "store_path": str(path),
        "fileCount": len(files_map),
    }

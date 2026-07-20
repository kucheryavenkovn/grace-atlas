# FILE: tools/grace_atlas/src/grace_atlas/roundtrip/fingerprints.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Content and semantic fingerprints for source files.
#   SCOPE: hash store under .grace-atlas/user/fingerprints.json
#   DEPENDS: hashlib, pathlib, json
#   LINKS: Phase 3D
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""File fingerprint store."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grace_atlas.config import AtlasConfig


def store_path(config: AtlasConfig) -> Path:
    return (config.repo_root / ".grace-atlas" / "user" / "fingerprints.json").resolve()


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def semantic_hash_python(text: str) -> str:
    """Rough semantic fingerprint: strip comments/blank lines, keep structure tokens."""
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # drop pure string-only noise lightly
        s = re.sub(r"#.*$", "", s).rstrip()
        if s:
            lines.append(s)
    payload = "\n".join(lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_python_markers(text: str) -> dict[str, Any]:
    module_ids = re.findall(r"\b(M-[A-Z0-9][-A-Z0-9_]*)\b", text)
    contracts = re.findall(r"START_CONTRACT:\s*(\S+)", text)
    blocks = re.findall(r"START_BLOCK_(\w+)", text)
    defs = re.findall(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)", text, re.M)
    symbols = [a or b for a, b in defs]
    return {
        "declaredModuleIds": sorted(set(module_ids)),
        "parsedContracts": sorted(set(contracts)),
        "parsedSemanticBlocks": sorted(set(blocks)),
        "publicSymbols": sorted(set(symbols))[:200],
    }


def fingerprint_file(path: Path, *, rel: str) -> dict[str, Any]:
    data = path.read_bytes()
    text = ""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    lang = "python" if path.suffix == ".py" else path.suffix.lstrip(".") or "unknown"
    markers = extract_python_markers(text) if lang == "python" else {
        "declaredModuleIds": [],
        "parsedContracts": [],
        "parsedSemanticBlocks": [],
        "publicSymbols": [],
    }
    return {
        "path": rel.replace("\\", "/"),
        "contentHash": content_hash(data),
        "semanticHash": semantic_hash_python(text) if lang == "python" else content_hash(data),
        "lastScanned": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "size": len(data),
        "language": lang,
        **markers,
    }


def load_store(config: AtlasConfig) -> dict[str, Any]:
    path = store_path(config)
    if not path.is_file():
        return {"schemaVersion": "1.0.0", "files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schemaVersion": "1.0.0", "files": {}}


def save_store(config: AtlasConfig, store: dict[str, Any]) -> Path:
    path = store_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path

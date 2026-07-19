# FILE: tools/grace_atlas/src/grace_atlas/parsers/_xmlutil.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Shared XML helpers for GRACE artifact parsers.
#   SCOPE: tag names, text, line maps, id splitting
#   DEPENDS: xml.etree, re
#   LINKS: tools/grace_atlas
#   ROLE: UTILITY
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT

"""Shared XML utilities."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET

from grace_atlas.model import SourceRef


def local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def text_of(elem: ET.Element | None, default: str = "") -> str:
    if elem is None:
        return default
    parts: list[str] = []
    if elem.text and elem.text.strip():
        parts.append(elem.text.strip())
    for child in elem:
        t = text_of(child)
        if t:
            parts.append(t)
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    return " ".join(parts).strip() or default


def child_text(elem: ET.Element, names: tuple[str, ...], default: str = "") -> str:
    for child in elem:
        if local(child.tag) in names:
            t = (child.text or "").strip()
            if t:
                return t
            # nested content
            nested = text_of(child)
            if nested:
                return nested
    return default


def attr(elem: ET.Element, *names: str, default: str = "") -> str:
    for n in names:
        if n in elem.attrib and elem.attrib[n] is not None:
            return str(elem.attrib[n]).strip()
    # case-insensitive fallback
    lower = {k.lower(): v for k, v in elem.attrib.items()}
    for n in names:
        if n.lower() in lower:
            return str(lower[n.lower()]).strip()
    return default


def iter_children(elem: ET.Element, *names: str) -> Iterator[ET.Element]:
    want = set(names)
    for child in elem:
        if local(child.tag) in want:
            yield child


def build_line_map(path: Path) -> dict[str, int]:
    """Map opening tag id/name fragments to approximate line numbers (best-effort)."""
    mapping: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return mapping
    # Match tags like <M-CLI ...>, <UC-001>, <V-M-CLI ...>, <Phase-10 ...>, <step-18.4 ...>
    pat = re.compile(
        r"<(?P<id>(?:M|V-M|UC|VF|DF|Phase|step|Gate-Phase|DS)-[A-Za-z0-9._-]+)\b"
    )
    for i, line in enumerate(lines, start=1):
        for m in pat.finditer(line):
            key = m.group("id")
            mapping.setdefault(key, i)
    return mapping


def source_ref(path: Path, entity_id: str, line_map: dict[str, int]) -> SourceRef:
    line = line_map.get(entity_id)
    return SourceRef(path=str(path), line_start=line, line_end=line)


def split_depends(raw: str) -> list[str]:
    if not raw:
        return []
    cleaned = raw.strip()
    if cleaned.lower() in {"none", "n/a", "-", "—"}:
        return []
    parts = re.split(r"[,;|/]+", cleaned)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Keep only module-like tokens as edges; external libs stay as properties.
        if re.match(r"^M-[A-Z0-9-]+$", p) or p.startswith("M-"):
            out.append(p)
    return out


def split_ids(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,;\s]+", raw.strip())
    return [p for p in parts if p]


def parse_xml(path: Path) -> ET.Element:
    tree = ET.parse(path)
    return tree.getroot()


def short_desc(text: str, limit: int = 400) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"

# FILE: tools/grace_atlas/src/grace_atlas/parsers/_xmlutil.py
# VERSION: 0.2.1
# START_MODULE_CONTRACT
#   PURPOSE: Shared XML helpers and bounded compatibility parsing for legacy GRACE artifacts.
#   SCOPE: tag names, text, line maps, id splitting; read-only repair of known syntax defects.
#   DEPENDS: xml.etree, re, warnings
#   LINKS: tools/grace_atlas; M-XML-COMPATIBILITY
#   ROLE: UTILITY
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT

"""Shared XML utilities."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET

from grace_atlas.model import SourceRef


class GraceXmlCompatibilityWarning(UserWarning):
    """A legacy GRACE artifact required a bounded in-memory syntax repair."""


class GraceXmlParseError(ValueError):
    """XML artifact cannot be parsed even after bounded compatibility repairs."""


@dataclass(frozen=True, slots=True)
class XmlCompatibilityFix:
    code: str
    count: int


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
        text = text_of(child)
        if text:
            parts.append(text)
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    return " ".join(parts).strip() or default


def child_text(elem: ET.Element, names: tuple[str, ...], default: str = "") -> str:
    for child in elem:
        if local(child.tag) in names:
            text = (child.text or "").strip()
            if text:
                return text
            nested = text_of(child)
            if nested:
                return nested
    return default


def attr(elem: ET.Element, *names: str, default: str = "") -> str:
    for name in names:
        if name in elem.attrib and elem.attrib[name] is not None:
            return str(elem.attrib[name]).strip()
    lower = {key.lower(): value for key, value in elem.attrib.items()}
    for name in names:
        if name.lower() in lower:
            return str(lower[name.lower()]).strip()
    return default


def iter_children(elem: ET.Element, *names: str) -> Iterator[ET.Element]:
    wanted = set(names)
    for child in elem:
        if local(child.tag) in wanted:
            yield child


def build_line_map(path: Path) -> dict[str, int]:
    """Map opening tag id/name fragments to approximate line numbers."""
    mapping: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return mapping
    pattern = re.compile(
        r"<(?P<id>(?:M|V-M|UC|VF|DF|Phase|step|Gate-Phase|DS)-[A-Za-z0-9._-]+)\b"
    )
    for line_number, line in enumerate(lines, start=1):
        for match in pattern.finditer(line):
            mapping.setdefault(match.group("id"), line_number)
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
    result: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.match(r"^M-[A-Z0-9-]+$", part) or part.startswith("M-"):
            result.append(part)
    return result


def split_ids(raw: str) -> list[str]:
    if not raw:
        return []
    return [part for part in re.split(r"[,;\s]+", raw.strip()) if part]


def sanitize_legacy_xml(text: str) -> tuple[str, tuple[XmlCompatibilityFix, ...]]:
    """Repair only known, mechanically unambiguous legacy syntax defects.

    The source file is never changed. The compatibility layer currently handles:
    - missing semicolons on the five predefined XML entities;
    - JSON-style escaped quotes accidentally copied into XML attributes;
    - a leaf element written on one line but closed with a sibling tag name.
    """
    result = text
    fixes: list[XmlCompatibilityFix] = []

    result, entity_count = re.subn(r"&(lt|gt|amp|quot|apos)(?!;)", r"&\1;", result)
    if entity_count:
        fixes.append(XmlCompatibilityFix("MISSING_ENTITY_SEMICOLON", entity_count))

    escaped_quote_count = result.count(r'\"') + result.count(r"\'")
    if escaped_quote_count:
        result = result.replace(r'\"', '"').replace(r"\'", "'")
        fixes.append(XmlCompatibilityFix("ESCAPED_ATTRIBUTE_QUOTE", escaped_quote_count))

    line_pattern = re.compile(
        r"^(?P<prefix>\s*)<(?P<open>[A-Za-z_][\w.:-]*)(?P<attrs>\s[^>]*)?>"
        r"(?P<body>.*)</(?P<close>[A-Za-z_][\w.:-]*)>(?P<suffix>\s*)$"
    )
    repaired_lines: list[str] = []
    mismatch_count = 0
    for line in result.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        bare = line[:-1] if newline else line
        match = line_pattern.match(bare)
        if (
            match
            and match.group("open") != match.group("close")
            and "<" not in match.group("body")
        ):
            bare = (
                f"{match.group('prefix')}<{match.group('open')}{match.group('attrs') or ''}>"
                f"{match.group('body')}</{match.group('open')}>{match.group('suffix')}"
            )
            mismatch_count += 1
        repaired_lines.append(bare + newline)
    if mismatch_count:
        result = "".join(repaired_lines)
        fixes.append(XmlCompatibilityFix("ONE_LINE_MISMATCHED_CLOSE", mismatch_count))

    return result, tuple(fixes)


def parse_xml(path: Path) -> ET.Element:
    text = path.read_text(encoding="utf-8", errors="strict")
    try:
        return ET.fromstring(text)
    except ET.ParseError as initial_error:
        compatible, fixes = sanitize_legacy_xml(text)
        if not fixes:
            raise GraceXmlParseError(f"{path}: {initial_error}") from initial_error
        try:
            root = ET.fromstring(compatible)
        except ET.ParseError as compatible_error:
            detail = ", ".join(f"{fix.code}={fix.count}" for fix in fixes)
            raise GraceXmlParseError(
                f"{path}: {compatible_error}; initial={initial_error}; compatibility={detail}"
            ) from compatible_error
        detail = ", ".join(f"{fix.code}={fix.count}" for fix in fixes)
        warnings.warn(
            f"{path}: parsed through legacy GRACE XML compatibility layer ({detail})",
            GraceXmlCompatibilityWarning,
            stacklevel=2,
        )
        return root


def short_desc(text: str, limit: int = 400) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"

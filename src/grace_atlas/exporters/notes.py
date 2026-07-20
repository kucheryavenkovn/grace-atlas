# FILE: tools/grace_atlas/src/grace_atlas/exporters/notes.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Stable note path / wiki-link helpers for Obsidian Graph View.
#   SCOPE: folder layout, Windows-safe names, type-scoped paths, edge section labels
#   DEPENDS: grace_atlas.model
#   LINKS: tools/grace_atlas
#   ROLE: UTILITY
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Note path and wikilink utilities (no parsing, no I/O)."""

from __future__ import annotations

import re

from grace_atlas.model import EdgeType, Node, NodeType

# Spec folder layout (capitalized, Graph-friendly, type-scoped to avoid ID collisions)
TYPE_FOLDERS: dict[str, str] = {
    NodeType.REQUIREMENT: "Requirements",
    NodeType.USE_CASE: "Use-Cases",
    NodeType.MODULE: "Modules",
    NodeType.VERIFICATION: "Verification",
    NodeType.CRITICAL_FLOW: "Flows",
    NodeType.DATA_FLOW: "Flows",
    NodeType.PHASE: "Phases",
    NodeType.STEP: "Steps",
    NodeType.OPERATIONAL_PACKET: "Operational-Packets",
    NodeType.SOURCE_FILE: "Source-Files",
    NodeType.TEST_FILE: "Tests",
    NodeType.CONTRACT: "Contracts",
    NodeType.SEMANTIC_BLOCK: "Semantic-Blocks",
    NodeType.TECHNOLOGY: "Technology",
    NodeType.EVIDENCE: "Evidence",
    NodeType.CONSTRAINT: "Constraints",
    NodeType.RISK: "Risks",
    NodeType.NON_GOAL: "Non-Goals",
    NodeType.PHASE_GATE: "Gates",
    NodeType.DEPLOYMENT: "Deployment",
    NodeType.ACTOR: "Actors",
}

TAG_BY_TYPE: dict[str, str] = {
    NodeType.REQUIREMENT: "grace/type/requirement",
    NodeType.USE_CASE: "grace/type/use_case",
    NodeType.MODULE: "grace/type/module",
    NodeType.VERIFICATION: "grace/type/verification",
    NodeType.CRITICAL_FLOW: "grace/type/verification",
    NodeType.DATA_FLOW: "grace/type/requirement",
    NodeType.PHASE: "grace/type/phase",
    NodeType.STEP: "grace/type/step",
    NodeType.OPERATIONAL_PACKET: "grace/type/operational_packet",
    NodeType.SOURCE_FILE: "grace/type/source_file",
    NodeType.TEST_FILE: "grace/type/test_file",
    NodeType.CONTRACT: "grace/type/contract",
    NodeType.SEMANTIC_BLOCK: "grace/type/semantic_block",
    NodeType.TECHNOLOGY: "grace/type/technology",
    NodeType.EVIDENCE: "grace/type/evidence",
    NodeType.CONSTRAINT: "grace/type/requirement",
    NodeType.RISK: "grace/type/requirement",
    NodeType.NON_GOAL: "grace/type/requirement",
    NodeType.PHASE_GATE: "grace/type/phase",
    NodeType.DEPLOYMENT: "grace/type/module",
    NodeType.ACTOR: "grace/type/requirement",
}

# Outgoing edge type → Russian section title (materialized wiki links)
OUTGOING_SECTIONS: dict[str, str] = {
    EdgeType.DEPENDS_ON: "Зависит от",
    EdgeType.IMPLEMENTED_IN: "Реализован в файлах",
    EdgeType.VERIFIED_BY: "Проверяется",
    EdgeType.TESTED_BY: "Тесты",
    EdgeType.IMPLEMENTS: "Реализует",
    EdgeType.RELATED_FLOW: "Связанные потоки",
    EdgeType.USES_USE_CASE: "Use cases",
    EdgeType.CONTAINS: "Содержит",
    EdgeType.BELONGS_TO: "Принадлежит",
    EdgeType.PRODUCES_EVIDENCE: "Evidence",
    EdgeType.CROSS_LINK: "Cross-links",
    EdgeType.LINKS_TO: "LINKS",
    EdgeType.REFERS_TO: "Ссылки",
    EdgeType.HAS_CONTRACT: "Контракты",
    EdgeType.HAS_BLOCK: "Семантические блоки",
    EdgeType.DOCUMENTED_IN: "Документация",
    EdgeType.CONSTRAINED_BY: "Ограничения",
    EdgeType.PLANNED_IN: "План",
    EdgeType.CHANGED_BY: "Изменяется",
}

# Incoming edge type → section (bidirectional navigation at note level)
INCOMING_SECTIONS: dict[str, str] = {
    EdgeType.DEPENDS_ON: "Зависят от этого",
    EdgeType.IMPLEMENTED_IN: "Модули, реализованные здесь",
    EdgeType.VERIFIED_BY: "Модули/шаги, которые проверяет",
    EdgeType.TESTED_BY: "Что покрывается этими тестами",
    EdgeType.IMPLEMENTS: "Реализуется модулями",
    EdgeType.RELATED_FLOW: "Ссылающиеся сущности",
    EdgeType.USES_USE_CASE: "Critical flows",
    EdgeType.CONTAINS: "Входит в",
    EdgeType.BELONGS_TO: "Шаги / дочерние",
    EdgeType.HAS_CONTRACT: "Файл-владелец",
    EdgeType.HAS_BLOCK: "Файл-владелец",
    EdgeType.LINKS_TO: "Ссылающиеся контракты",
    EdgeType.CROSS_LINK: "Входящие cross-links",
    EdgeType.REFERS_TO: "Входящие ссылки",
    EdgeType.PRODUCES_EVIDENCE: "Verification",
}


_PATH_SEP_TOKEN = "¶SEP¶"  # temporary token (not a Windows-forbidden char)


def safe_filename(name: str, *, max_len: int = 120) -> str:
    """Windows-safe deterministic file stem (no path separators)."""
    s = (name or "").strip()
    s = s.replace("\\", "/")
    # Preserve path boundaries as __ (token survives forbidden-char scrubbing)
    s = s.replace("/", _PATH_SEP_TOKEN)
    s = re.sub(r'[<>:"|?*\x00-\x1f]', "_", s)
    s = s.replace(":", _PATH_SEP_TOKEN)
    s = re.sub(r"\s+", "_", s)
    s = s.replace(_PATH_SEP_TOKEN, "__")
    s = s.strip("._")
    if not s:
        s = "unnamed"
    if len(s) > max_len:
        import hashlib

        digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]
        s = s[: max_len - 9] + "_" + digest
    return s


def file_note_stem(rel_path: str) -> str:
    """src/video2pptx/foo.py → src__video2pptx__foo.py"""
    rel = (rel_path or "").replace("\\", "/").lstrip("./")
    return safe_filename(rel)


def note_stem(node: Node) -> str:
    """Stable stem inside type folder (no folder, no .md)."""
    if node.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
        rel = str(node.properties.get("path") or node.name or node.id.removeprefix("file:"))
        return file_note_stem(rel)
    # Prefix type-colliding free-form ids (constraint-1, risk-1) with type already in folder
    return safe_filename(node.id)


def note_folder(node: Node) -> str:
    return TYPE_FOLDERS.get(node.type, "Other")


def note_relpath(node: Node) -> str:
    """Vault-relative path with .md, using forward slashes."""
    return f"{note_folder(node)}/{note_stem(node)}.md"


def note_wikilink_target(node: Node) -> str:
    """Path used inside [[...]] without .md — type-scoped to avoid collisions."""
    return f"{note_folder(node)}/{note_stem(node)}"


def wikilink(node: Node, label: str | None = None) -> str:
    target = note_wikilink_target(node)
    display = label if label is not None else (node.id if node.id != note_stem(node) else node.name or node.id)
    if display and display != target and display != note_stem(node):
        return f"[[{target}|{display}]]"
    return f"[[{target}]]"


def wikilink_by_id(graph_nodes: dict[str, Node], node_id: str, label: str | None = None) -> str:
    node = graph_nodes.get(node_id)
    if node is None:
        # Unresolved: still emit a stable path under Other for Graph visibility of orphans
        stem = safe_filename(node_id)
        return f"[[Other/{stem}|{label or node_id}]]"
    return wikilink(node, label)


def tags_for(node: Node) -> list[str]:
    tags = ["grace-atlas", "grace/generated"]
    t = TAG_BY_TYPE.get(node.type)
    if t:
        tags.append(t)
    status = (node.status or "").strip().lower().replace(" ", "-")
    if status:
        tags.append(f"grace/status/{safe_filename(status, max_len=40)}")
    return tags


def grace_type_slug(node_type: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", node_type.lower()).strip("-")

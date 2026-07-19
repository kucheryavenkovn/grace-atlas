# FILE: tools/grace_atlas/src/grace_atlas/parsers/source_markup.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Scan source/tests for GRACE MODULE_CONTRACT, CONTRACT, BLOCK, LINKS markup.
#   SCOPE: Python files matching include/exclude globs
#   DEPENDS: grace_atlas.model, config
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Parse GRACE semantic markup inside source files."""

from __future__ import annotations

import re
from pathlib import Path

from grace_atlas.config import AtlasConfig
from grace_atlas.model import (
    AtlasGraph,
    Edge,
    EdgeType,
    Node,
    NodeType,
    Provenance,
    SourceRef,
)
from grace_atlas.parsers._xmlutil import short_desc

MODULE_CONTRACT_RE = re.compile(
    r"#\s*START_MODULE_CONTRACT\s*(.*?)\s*#\s*END_MODULE_CONTRACT",
    re.DOTALL,
)
CONTRACT_RE = re.compile(
    r"#\s*START_CONTRACT:\s*(?P<name>[A-Za-z0-9_.]+)\s*(.*?)\s*#\s*END_CONTRACT:\s*(?P=name)",
    re.DOTALL,
)
BLOCK_RE = re.compile(
    r"#\s*START_BLOCK_(?P<name>[A-Za-z0-9_]+)\b",
)
LINKS_RE = re.compile(r"LINKS:\s*(.+)")
PURPOSE_RE = re.compile(r"PURPOSE:\s*(.+)")
DEPENDS_RE = re.compile(r"DEPENDS:\s*(.+)")
ROLE_RE = re.compile(r"ROLE:\s*(.+)")


def _iter_source_files(config: AtlasConfig) -> list[Path]:
    root = config.repo_root
    files: set[Path] = set()
    for pattern in config.source_include:
        for p in root.glob(pattern):
            if p.is_file():
                files.add(p.resolve())

    excluded: set[Path] = set()
    for pattern in config.source_exclude:
        for p in root.glob(pattern):
            if p.is_file():
                excluded.add(p.resolve())
            elif p.is_dir():
                excluded.update(x.resolve() for x in p.rglob("*") if x.is_file())

    # Path-part exclude for common dirs
    skip_parts = {".git", ".venv", "build", "dist", ".grace-atlas", "__pycache__", "node_modules"}
    out: list[Path] = []
    for f in sorted(files):
        if f in excluded:
            continue
        if any(part in skip_parts for part in f.parts):
            continue
        out.append(f)
    return out


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _parse_links(blob: str) -> list[str]:
    links: list[str] = []
    for m in LINKS_RE.finditer(blob):
        raw = m.group(1).strip()
        for part in re.split(r"[,;]", raw):
            part = part.strip()
            if part:
                links.append(part)
    return links


def parse_source_markup(config: AtlasConfig, graph: AtlasGraph) -> None:
    root = config.repo_root
    for path in _iter_source_files(config):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = _rel(path, root)
        is_test = rel.startswith("tests/") or "/tests/" in rel or rel.startswith("test_")
        file_id = f"file:{rel}"
        graph.add_node(
            Node(
                id=file_id,
                name=rel,
                type=NodeType.TEST_FILE if is_test else NodeType.SOURCE_FILE,
                source="source-markup",
                source_ref=SourceRef(path=rel, line_start=1),
                properties={"path": rel, "exists": True},
            )
        )

        for m in MODULE_CONTRACT_RE.finditer(text):
            blob = m.group(1)
            purpose_m = PURPOSE_RE.search(blob)
            purpose = purpose_m.group(1).strip() if purpose_m else ""
            depends_m = DEPENDS_RE.search(blob)
            depends = depends_m.group(1).strip() if depends_m else ""
            role_m = ROLE_RE.search(blob)
            role = role_m.group(1).strip() if role_m else ""
            links = _parse_links(blob)
            line_start = _line_of(text, m.start())
            line_end = _line_of(text, m.end())
            contract_id = f"contract:{rel}:MODULE"
            graph.add_node(
                Node(
                    id=contract_id,
                    name=f"MODULE_CONTRACT ({rel})",
                    type=NodeType.CONTRACT,
                    description=short_desc(purpose),
                    source="source-markup",
                    source_ref=SourceRef(path=rel, line_start=line_start, line_end=line_end),
                    properties={
                        "kind": "module_contract",
                        "depends": depends,
                        "role": role,
                        "links": links,
                        "file": rel,
                    },
                )
            )
            graph.add_edge(
                Edge(
                    source=file_id,
                    target=contract_id,
                    type=EdgeType.HAS_CONTRACT,
                    relation_source="START_MODULE_CONTRACT",
                    provenance=Provenance.DECLARED,
                    artifact_path=rel,
                )
            )
            for link in links:
                target = link
                if re.match(r"^M-[A-Z0-9-]+$", link) or link.startswith("M-"):
                    if link not in graph.nodes:
                        graph.add_node(
                            Node(
                                id=link,
                                name=link,
                                type=NodeType.MODULE,
                                source="source-markup",
                                properties={"stub": True},
                            )
                        )
                    graph.add_edge(
                        Edge(
                            source=link,
                            target=file_id,
                            type=EdgeType.IMPLEMENTED_IN,
                            relation_source="MODULE_CONTRACT LINKS",
                            provenance=Provenance.DECLARED,
                            artifact_path=rel,
                        )
                    )
                    graph.add_edge(
                        Edge(
                            source=contract_id,
                            target=link,
                            type=EdgeType.LINKS_TO,
                            relation_source="LINKS",
                            provenance=Provenance.DECLARED,
                            artifact_path=rel,
                        )
                    )
                else:
                    graph.add_edge(
                        Edge(
                            source=contract_id,
                            target=target if target in graph.nodes else file_id,
                            type=EdgeType.LINKS_TO,
                            relation_source="LINKS",
                            provenance=Provenance.DECLARED,
                            description=link,
                            artifact_path=rel,
                        )
                    )

        for m in CONTRACT_RE.finditer(text):
            name = m.group("name")
            blob = m.group(2)
            purpose_m = PURPOSE_RE.search(blob)
            purpose = purpose_m.group(1).strip() if purpose_m else ""
            links = _parse_links(blob)
            line_start = _line_of(text, m.start())
            line_end = _line_of(text, m.end())
            contract_id = f"contract:{rel}:{name}"
            graph.add_node(
                Node(
                    id=contract_id,
                    name=name,
                    type=NodeType.CONTRACT,
                    description=short_desc(purpose),
                    source="source-markup",
                    source_ref=SourceRef(path=rel, line_start=line_start, line_end=line_end),
                    properties={"kind": "function_contract", "file": rel, "links": links},
                )
            )
            graph.add_edge(
                Edge(
                    source=file_id,
                    target=contract_id,
                    type=EdgeType.HAS_CONTRACT,
                    relation_source="START_CONTRACT",
                    provenance=Provenance.DECLARED,
                    artifact_path=rel,
                )
            )
            for link in links:
                if re.match(r"^M-[A-Z0-9-]+$", link) or link.startswith("M-"):
                    if link not in graph.nodes:
                        graph.add_node(
                            Node(
                                id=link,
                                name=link,
                                type=NodeType.MODULE,
                                source="source-markup",
                                properties={"stub": True},
                            )
                        )
                    graph.add_edge(
                        Edge(
                            source=contract_id,
                            target=link,
                            type=EdgeType.LINKS_TO,
                            relation_source="LINKS",
                            provenance=Provenance.DECLARED,
                            artifact_path=rel,
                        )
                    )

        for m in BLOCK_RE.finditer(text):
            name = m.group("name")
            line_start = _line_of(text, m.start())
            # Find matching END
            end_pat = re.compile(rf"#\s*END_BLOCK_{re.escape(name)}\b")
            end_m = end_pat.search(text, m.end())
            line_end = _line_of(text, end_m.start()) if end_m else line_start
            block_id = f"block:{rel}:{name}"
            graph.add_node(
                Node(
                    id=block_id,
                    name=name,
                    type=NodeType.SEMANTIC_BLOCK,
                    source="source-markup",
                    source_ref=SourceRef(path=rel, line_start=line_start, line_end=line_end),
                    properties={"file": rel},
                )
            )
            graph.add_edge(
                Edge(
                    source=file_id,
                    target=block_id,
                    type=EdgeType.HAS_BLOCK,
                    relation_source="START_BLOCK",
                    provenance=Provenance.DECLARED,
                    artifact_path=rel,
                )
            )

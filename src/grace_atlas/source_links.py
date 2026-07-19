# FILE: tools/grace_atlas/src/grace_atlas/source_links.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Resolve source paths and build vscode://file deep-links (Windows-safe URI encoding).
#   SCOPE: existence checks; vscode URI with optional line/column; markdown open links
#   DEPENDS: pathlib, urllib.parse
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Source path resolution and editor deep-links (read-only)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from grace_atlas.config import AtlasConfig
from grace_atlas.model import AtlasGraph, NodeType


def link_source_and_test_files(config: AtlasConfig, graph: AtlasGraph) -> None:
    """Annotate SourceFile/TestFile nodes with filesystem existence (no writes)."""
    root = config.repo_root
    for node in list(graph.nodes.values()):
        if node.type not in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
            continue
        rel = str(node.properties.get("path") or node.name or "")
        if not rel or rel.startswith("file:"):
            rel = node.id.removeprefix("file:")
        rel = rel.replace("\\", "/").strip()
        if not rel:
            continue
        node.properties["path"] = rel
        abs_path = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
        exists = abs_path.exists()
        node.properties["exists"] = exists
        node.properties["is_dir"] = abs_path.is_dir() if exists else False
        node.properties["absolute_path"] = str(abs_path)
        if not exists:
            node.properties["missing"] = True


def path_to_vscode_file_component(absolute_path: str | Path) -> str:
    """
    Convert an absolute filesystem path to the path component of vscode://file/...

    Windows: C:\\Users\\tux\\a.py → /C:/Users/tux/a.py (then percent-encoded)
    POSIX:   /home/u/a.py → /home/u/a.py
    """
    p = Path(absolute_path)
    # Prefer resolved absolute path when it exists; otherwise keep as given.
    try:
        if p.exists():
            p = p.resolve()
        elif not p.is_absolute():
            p = p.resolve()
    except OSError:
        p = Path(str(absolute_path))

    as_posix = str(p).replace("\\", "/")
    # Drive letter Windows path
    if len(as_posix) >= 2 and as_posix[1] == ":":
        as_posix = "/" + as_posix
    elif not as_posix.startswith("/"):
        as_posix = "/" + as_posix
    # Encode everything except path separators and colon (drive)
    return quote(as_posix, safe="/:")


def vscode_uri(
    absolute_path: str | Path,
    line: int | None = None,
    column: int | None = None,
) -> str:
    """
    Build vscode://file/ABSOLUTE_PATH[:LINE[:COLUMN]].

    Do not append a fictitious line when line is None/0.
    Column is only appended when line is a positive integer.
    """
    path_part = path_to_vscode_file_component(absolute_path)
    uri = f"vscode://file{path_part}"
    if line is not None and int(line) > 0:
        uri = f"{uri}:{int(line)}"
        if column is not None and int(column) > 0:
            uri = f"{uri}:{int(column)}"
    return uri


def file_open_link(
    absolute_path: str | Path,
    *,
    line: int | None = None,
    column: int | None = None,
    label: str | None = None,
    vscode_enabled: bool = True,
) -> str:
    """Markdown link to open a file (VS Code URI when enabled)."""
    p = Path(absolute_path)
    text = label or p.name
    if line is not None and int(line) > 0:
        text = f"{text}:{int(line)}"
        if column is not None and int(column) > 0:
            text = f"{text}:{int(column)}"
    if vscode_enabled:
        return f"[{text}]({vscode_uri(p, line, column)})"
    return f"`{str(p).replace(chr(92), '/')}" + (f":{line}" if line else "") + "`"


def obsidian_open_uri(absolute_path: str | Path) -> str:
    """obsidian://open?path=<absolute-uri-encoded-path> (Windows-safe)."""
    p = Path(absolute_path)
    try:
        if p.exists():
            p = p.resolve()
    except OSError:
        pass
    raw = str(p)
    # Obsidian expects path query with full absolute path, URI-encoded
    return "obsidian://open?path=" + quote(raw, safe="")

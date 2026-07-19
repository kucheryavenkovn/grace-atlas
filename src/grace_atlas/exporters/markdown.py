# FILE: tools/grace_atlas/src/grace_atlas/exporters/markdown.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Render Atlas nodes as Obsidian Markdown notes with material wiki-links for Graph View.
#   SCOPE: entity notes, type indexes, Home (no star-hub), diagnostic indexes
#   DEPENDS: exporters.notes, source_links, model
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Markdown note rendering for Obsidian Graph View."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from grace_atlas.config import AtlasConfig
from grace_atlas.exporters.notes import (
    INCOMING_SECTIONS,
    OUTGOING_SECTIONS,
    TYPE_FOLDERS,
    grace_type_slug,
    note_relpath,
    note_stem,
    note_wikilink_target,
    tags_for,
    wikilink,
)
from grace_atlas.model import AtlasGraph, Edge, EdgeType, Node, NodeType
from grace_atlas.source_links import file_open_link

GENERATED_BANNER = (
    "<!-- GRACE Atlas: GENERATED FILE. Do not edit by hand — manual changes will be lost on rebuild. -->"
)


def _yaml_escape(value: str) -> str:
    s = str(value) if value is not None else ""
    if s == "":
        return '""'
    if any(c in s for c in (":", "#", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`", "\n")):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def render_frontmatter(node: Node) -> str:
    tags = tags_for(node)
    lines = [
        "---",
        f"grace_type: {grace_type_slug(node.type)}",
        f"grace_id: {_yaml_escape(node.id)}",
        f"status: {_yaml_escape(node.status or '')}",
        "generated: true",
        f"source: {_yaml_escape(node.source or '')}",
        "tags:",
    ]
    for t in tags:
        lines.append(f"  - {t}")
    if node.source_ref:
        lines.append(f"artifact: {_yaml_escape(node.source_ref.path)}")
        if node.source_ref.line_start:
            lines.append(f"line: {node.source_ref.line_start}")
    path = node.properties.get("path")
    if path:
        lines.append(f"path: {_yaml_escape(str(path))}")
    lines.append("---")
    return "\n".join(lines)


def _group_edges(edges: list[Edge], *, outgoing: bool) -> dict[str, list[Edge]]:
    grouped: dict[str, list[Edge]] = defaultdict(list)
    for e in edges:
        grouped[e.type].append(e)
    # stable order
    for k in grouped:
        grouped[k] = sorted(grouped[k], key=lambda e: (e.target if outgoing else e.source, e.id))
    return dict(sorted(grouped.items(), key=lambda kv: kv[0]))


def _edge_sections(
    graph: AtlasGraph,
    node: Node,
    *,
    outgoing: bool,
) -> list[str]:
    lines: list[str] = []
    selected: list[Edge] = []
    for e in graph.edges:
        if outgoing and e.source == node.id:
            selected.append(e)
        elif not outgoing and e.target == node.id:
            selected.append(e)
    if not selected:
        return lines

    titles = OUTGOING_SECTIONS if outgoing else INCOMING_SECTIONS
    grouped = _group_edges(selected, outgoing=outgoing)
    for etype, edges in grouped.items():
        title = titles.get(etype, etype)
        lines.append(f"## {title}")
        lines.append("")
        for e in edges:
            other_id = e.target if outgoing else e.source
            other = graph.get(other_id)
            if other is None:
                lines.append(f"- `{etype}` → `[[Other/{other_id}]]` _(unresolved)_")
                continue
            label = other.id
            prov = ""
            if e.provenance.value != "declared":
                prov = f" `({e.provenance.value})`"
            desc = f" — {e.description}" if e.description and e.description != e.type else ""
            lines.append(f"- {wikilink(other, label)}{prov}{desc}")
        lines.append("")
    return lines


def _source_section(node: Node, config: AtlasConfig) -> list[str]:
    from pathlib import Path

    lines: list[str] = ["## Источник", ""]
    if node.source_ref and node.source_ref.path:
        art = node.source_ref.path
        line = node.source_ref.line_start
        lines.append(f"- GRACE / artifact: `{art}`" + (f" (line {line})" if line else ""))
        try:
            p = Path(art)
            if not p.is_absolute():
                p = config.repo_root / art
            if p.exists() and p.is_file():
                lines.append(
                    f"- Open artifact: {file_open_link(p, line=line, label=art, vscode_enabled=config.vscode_enabled)}"
                )
        except OSError:
            pass
    elif node.source:
        lines.append(f"- Data source role: `{node.source}`")
    else:
        lines.append("- _(source not recorded)_")
    lines.append("")
    return lines


def _code_open_section(node: Node, config: AtlasConfig) -> list[str]:
    lines: list[str] = []
    from pathlib import Path

    if node.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
        rel = node.properties.get("path") or node.name
        abs_p = node.properties.get("absolute_path")
        lines.append("## Открыть в редакторе")
        lines.append("")
        lines.append(f"- Relative path: `{rel}`")
        if abs_p and node.properties.get("exists"):
            lines.append(
                f"- VS Code: {file_open_link(abs_p, label=str(rel), vscode_enabled=config.vscode_enabled)}"
            )
        else:
            lines.append(f"- Missing on disk: `{abs_p or rel}`")
        lines.append("")
        return lines

    if node.type in {NodeType.CONTRACT, NodeType.SEMANTIC_BLOCK}:
        file_rel = node.properties.get("file") or (node.source_ref.path if node.source_ref else "")
        line = node.source_ref.line_start if node.source_ref else None
        if file_rel:
            abs_p = (config.repo_root / file_rel).resolve()
            lines.append("## Открыть в редакторе")
            lines.append("")
            if abs_p.exists():
                lines.append(
                    f"- VS Code: {file_open_link(abs_p, line=line, label=f'{file_rel}' + (f':{line}' if line else ''), vscode_enabled=config.vscode_enabled)}"
                )
            else:
                lines.append(f"- File: `{file_rel}` _(missing)_")
            lines.append("")
        return lines

    paths = list(node.properties.get("paths") or [])
    if paths:
        lines.append("## Исходные файлы (пути)")
        lines.append("")
        for p in paths:
            abs_p = (config.repo_root / p).resolve()
            if abs_p.exists():
                lines.append(f"- {file_open_link(abs_p, label=p, vscode_enabled=config.vscode_enabled)}")
            else:
                lines.append(f"- `{p}` _(missing)_")
        lines.append("")
    return lines


def render_node_note(node: Node, graph: AtlasGraph, config: AtlasConfig) -> str:
    lines: list[str] = [
        GENERATED_BANNER,
        "",
        render_frontmatter(node),
        "",
        f"# {node.id}",
        "",
    ]
    if node.name and node.name != node.id:
        lines.append(f"**{node.name}**")
        lines.append("")
    lines.append("## Назначение")
    lines.append("")
    lines.append(node.description or "_(нет описания)_")
    lines.append("")
    lines.append("## Статус")
    lines.append("")
    lines.append(f"- `{node.status or 'unknown'}`")
    lines.append(f"- type: `{node.type}`")
    lines.append(f"- note: `{note_wikilink_target(node)}`")
    lines.append("")

    lines.extend(_source_section(node, config))
    lines.extend(_code_open_section(node, config))

    # Materialized relationship sections (Graph View edges)
    out_sec = _edge_sections(graph, node, outgoing=True)
    in_sec = _edge_sections(graph, node, outgoing=False)
    if out_sec or in_sec:
        lines.extend(out_sec)
        lines.extend(in_sec)
    else:
        lines.append("## Отношения")
        lines.append("")
        lines.append("_Нет рёбер в графе (orphan / isolated)._")
        lines.append("")

    # Key properties (non-graph)
    skip = {"stub", "paths", "test_paths", "absolute_path", "exists", "missing", "is_dir", "file", "links"}
    props = {k: v for k, v in (node.properties or {}).items() if k not in skip and v not in (None, "", [], {})}
    if props:
        lines.append("## Свойства")
        lines.append("")
        for k in sorted(props.keys()):
            v = props[k]
            if isinstance(v, list):
                lines.append(f"- **{k}**:")
                for item in v[:40]:
                    lines.append(f"  - `{item}`")
            else:
                lines.append(f"- **{k}**: `{v}`")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by GRACE Atlas (read-only projection). `generated: true`_")
    lines.append("")
    return "\n".join(lines)


def render_index(title: str, nodes: Iterable[Node], *, graph_tag: str = "grace/index") -> str:
    nodes_list = sorted(nodes, key=lambda n: n.id)
    lines = [
        GENERATED_BANNER,
        "",
        "---",
        "generated: true",
        f"tags: [grace-atlas, {graph_tag}, grace/index]",
        "---",
        "",
        f"# {title}",
        "",
        f"Count: **{len(nodes_list)}**",
        "",
        "> Index pages are navigational. Exclude tag `grace/index` from Graph View if they clutter the domain graph.",
        "",
    ]
    for n in nodes_list:
        status = f" `{n.status}`" if n.status else ""
        lines.append(f"- {wikilink(n, n.id)}{status}")
    lines.append("")
    return "\n".join(lines)


def render_home(
    graph: AtlasGraph,
    config: AtlasConfig,
    *,
    generated_at: str,
    gap_summary: dict,
) -> str:
    stats = graph.stats()
    arts = graph.meta.get("artifacts") or {}
    lines = [
        GENERATED_BANNER,
        "",
        "---",
        "generated: true",
        "tags: [grace-atlas, grace/home]",
        f"project: {_yaml_escape(config.project_name)}",
        f"generated_at: {_yaml_escape(generated_at)}",
        "---",
        "",
        f"# GRACE Atlas — {config.project_name}",
        "",
        f"Generated at: **{generated_at}** (UTC)",
        "",
        "Read-only projection of GRACE artifacts. GRACE XML and source code remain the source of truth.",
        "",
        "## Canvas",
        "",
        "> Open **`.canvas`** files (not plain notes). Links include the `.canvas` extension so Obsidian does not create empty `.md` stubs.",
        "",
        "- [[Canvas/Project-Overview.canvas|Project Overview]]",
        "- [[Canvas/Current-Phase.canvas|Current Phase]]",
        "- [[Canvas/User-Journey.canvas|User Journey]]",
        "- [[Canvas/Requirement-Traceability.canvas|Requirement Traceability]]",
        "- [[Canvas/Verification-Gaps.canvas|Verification Gaps]]",
        "- [[Canvas/_index|Canvas index]]",
        "",

        "## Diagnostics",
        "",
        "- [[Diagnostics/Summary]]",
        "- [[Diagnostics/Broken-References]]",
        "- [[Diagnostics/Orphan-Requirements]]",
        "- [[Diagnostics/Unverified-Modules]]",
        "- [[Diagnostics/Unmapped-Files]]",
        "- [[Diagnostics/Ambiguous-Links]]",
        "",
        "## Indexes (exclude `grace/index` from Graph View)",
        "",
        "- [[Modules/_index|Modules]]",
        "- [[Use-Cases/_index|Use cases]]",
        "- [[Verification/_index|Verification]]",
        "- [[Phases/_index|Phases]]",
        "- [[Source-Files/_index|Source files]]",
        "- [[Tests/_index|Tests]]",
        "",
        "## Discovered GRACE artifacts",
        "",
    ]
    for key in (
        "requirements",
        "development_plan",
        "knowledge_graph",
        "verification_plan",
        "operational_packets",
        "technology",
    ):
        lines.append(f"- **{key}**: `{arts.get(key)}`")
    lines.append("")
    lines.append("## Entity counts")
    lines.append("")
    lines.append(f"- **Nodes**: {stats['nodes']}")
    lines.append(f"- **Edges**: {stats['edges']}")
    lines.append("")
    for t, c in (stats.get("nodes_by_type") or {}).items():
        lines.append(f"- `{t}`: {c}")
    lines.append("")
    lines.append("## Edges by type")
    lines.append("")
    for t, c in (stats.get("edges_by_type") or {}).items():
        lines.append(f"- `{t}`: {c}")
    lines.append("")
    lines.append("## Traceability / diagnostics snapshot")
    lines.append("")
    lines.append(f"- Findings: **{gap_summary.get('findings', 0)}**")
    lines.append(f"- By severity: `{gap_summary.get('by_severity', {})}`")
    lines.append(f"- By code: `{gap_summary.get('by_code', {})}`")
    lines.append(f"- Missing files: {gap_summary.get('missing_files', 0)}")
    lines.append(f"- Stub modules: {gap_summary.get('stub_modules', 0)}")
    lines.append(f"- Unverified modules: {gap_summary.get('unverified_modules', 0)}")
    lines.append(f"- Broken references: {gap_summary.get('broken_references', 0)}")
    lines.append("")
    lines.append("## Rebuild commands")
    lines.append("")
    lines.append("```powershell")
    lines.append("$env:PYTHONPATH = \"tools/grace_atlas/src\"")
    lines.append("python -m grace_atlas build --project-root .")
    lines.append("# or:")
    lines.append("python tools/grace_atlas.py build")
    lines.append("```")
    lines.append("")
    lines.append("## Graph View tips")
    lines.append("")
    lines.append("- Open **Graph view** from the left ribbon for the global cloud.")
    lines.append("- Open a note → command palette → **Open local graph** for neighborhood.")
    lines.append("- Filter: `tag:#grace/module`, `tag:#grace/file`, `tag:#grace/verification`, `path:Modules`.")
    lines.append("- Exclude `tag:#grace/index` and `tag:#grace/home` if navigation notes dominate.")
    lines.append("")
    lines.append("---")
    lines.append("_Home intentionally does **not** link every entity (avoids star-graph distortion)._")
    lines.append("")
    return "\n".join(lines)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Re-export for exporters
__all__ = [
    "TYPE_FOLDERS",
    "GENERATED_BANNER",
    "note_relpath",
    "note_stem",
    "wikilink",
    "render_node_note",
    "render_index",
    "render_home",
    "utc_now_iso",
]

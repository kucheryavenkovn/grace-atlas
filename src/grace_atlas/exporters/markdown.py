# FILE: tools/grace_atlas/src/grace_atlas/exporters/markdown.py
# VERSION: 0.3.0
# PURPOSE: Human-oriented Obsidian notes with unified properties + wiki-links for Local Graph.

"""Markdown note rendering for Obsidian workbench."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from grace_atlas.config import AtlasConfig
from grace_atlas.exporters.notes import (
    INCOMING_SECTIONS,
    OUTGOING_SECTIONS,
    TYPE_FOLDERS,
    grace_type_slug,
    note_relpath,
    note_wikilink_target,
    tags_for,
    wikilink,
)
from grace_atlas.model import AtlasGraph, Edge, EdgeType, Node, NodeType
from grace_atlas.source_links import file_open_link

GENERATED_BANNER = (
    "<!-- GRACE Atlas: СГЕНЕРИРОВАННЫЙ ФАЙЛ. Не редактируйте вручную — изменения пропадут при rebuild. -->"
)
HUMAN_BANNER = "> Этот файл сгенерирован GRACE Atlas. Ручные изменения могут быть потеряны при rebuild."


def _yaml_escape(value: str) -> str:
    s = str(value) if value is not None else ""
    if s == "":
        return '""'
    if any(c in s for c in (":", "#", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`", "\n")):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _yaml_value(v: Any, indent: int = 0) -> list[str]:
    sp = "  " * indent
    if isinstance(v, bool):
        return [f"{sp}{'true' if v else 'false'}"]
    if isinstance(v, (int, float)):
        return [f"{sp}{v}"]
    if isinstance(v, list):
        if not v:
            return [f"{sp}[]"]
        lines: list[str] = []
        for item in v:
            if isinstance(item, (list, dict)):
                lines.append(f"{sp}-")
                lines.extend(_yaml_value(item, indent + 1))
            else:
                lines.append(f"{sp}- {_yaml_escape(str(item))}")
        return lines
    return [f"{sp}{_yaml_escape(str(v))}"]


def render_frontmatter(node: Node) -> str:
    """Unified workbench property schema."""
    props = node.properties or {}
    grace_type = props.get("grace_type") or grace_type_slug(node.type)
    display = props.get("display_name") or node.name or node.id
    tags = tags_for(node)
    # ensure type tag form grace/type/<x>
    type_tag = f"grace/type/{grace_type}"
    if type_tag not in tags:
        tags.insert(0, type_tag)
    if props.get("requirement_type"):
        rt = f"grace/requirement/{props['requirement_type']}"
        if rt not in tags:
            tags.append(rt)
    if props.get("has_traceability_gap"):
        tags.append("grace/gap")

    lines = ["---"]
    kv: list[tuple[str, Any]] = [
        ("grace_id", node.id),
        ("grace_type", grace_type),
        ("display_name", display),
        ("status", node.status or ""),
        ("source_state", props.get("source_state") or "declared"),
        ("generated", True),
        ("source_file", props.get("source_file") or (node.source_ref.path if node.source_ref else "")),
    ]
    if props.get("source_line") or (node.source_ref and node.source_ref.line_start):
        kv.append(("source_line", props.get("source_line") or node.source_ref.line_start))

    # typed optional lists / fields
    for key in (
        "requirement_type",
        "priority",
        "parent",
        "children",
        "refines",
        "refined_by",
        "belongs_to_use_case",
        "implemented_by",
        "implemented_in",
        "implements",
        "depends_on",
        "dependency_of",
        "verified_by",
        "verifies",
        "tested_by",
        "planned_in",
        "evidence",
        "acceptance_criteria",
        "contracts",
        "semantic_blocks",
        "test_files",
        "commands",
        "required_markers",
        "last_known_result",
        "gap_types",
        "has_traceability_gap",
        "edge_count",
        "path",
        "module",
        "bc_parent",
        "requirement_type_note",
    ):
        if key in props and props[key] not in (None, "", [], {}):
            kv.append((key, props[key]))

    for k, v in kv:
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines.extend(_yaml_value(v, 1))
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: {_yaml_escape(str(v))}")

    lines.append("tags:")
    for t in tags:
        lines.append(f"  - {t}")
    lines.append("---")
    return "\n".join(lines)


def _group_edges(edges: list[Edge], *, outgoing: bool) -> dict[str, list[Edge]]:
    grouped: dict[str, list[Edge]] = defaultdict(list)
    for e in edges:
        grouped[e.type].append(e)
    for k in grouped:
        grouped[k] = sorted(grouped[k], key=lambda e: (e.target if outgoing else e.source, e.id))
    return dict(sorted(grouped.items(), key=lambda kv: kv[0]))


def _edge_sections(graph: AtlasGraph, node: Node, *, outgoing: bool) -> list[str]:
    lines: list[str] = []
    selected = [
        e
        for e in graph.edges
        if (outgoing and e.source == node.id) or ((not outgoing) and e.target == node.id)
    ]
    if not selected:
        return lines
    titles = OUTGOING_SECTIONS if outgoing else INCOMING_SECTIONS
    for etype, edges in _group_edges(selected, outgoing=outgoing).items():
        title = titles.get(etype, etype)
        lines.append(f"## {title}")
        lines.append("")
        for e in edges:
            other_id = e.target if outgoing else e.source
            other = graph.get(other_id)
            if other is None:
                lines.append(f"- `{etype}` → `[[Other/{other_id}]]` _(unresolved)_")
                continue
            prov = f" `({e.provenance.value})`" if e.provenance.value != "declared" else ""
            desc = f" — {e.description}" if e.description and e.description != e.type else ""
            lines.append(f"- {wikilink(other, other.id)}{prov}{desc}")
        lines.append("")
    return lines


def _problems_section(node: Node) -> list[str]:
    gaps = node.properties.get("gap_types") or []
    if not gaps and not node.properties.get("has_traceability_gap"):
        return []
    lines = ["## Проблемы", ""]
    if not gaps:
        lines.append("- Есть флаг `has_traceability_gap`, детали см. Diagnostics.")
    for g in gaps:
        lines.append(f"- `{g}`")
    note = node.properties.get("requirement_type_note")
    if note:
        lines.append(f"- {note}")
    lines.append("")
    return lines


def _nav_section(node: Node, config: AtlasConfig) -> list[str]:
    lines = ["## Навигация", ""]
    lines.append("- Local Graph: палитра команд → **Open local graph** (глубина 1–2).")
    lines.append("- Workbench: [[Dashboards/Workbench]].")
    lines.append("- Трассируемость: [[Dashboards/Traceability-Matrix]].")
    if node.source_ref and node.source_ref.path:
        lines.append(f"- XML/исходный артефакт: `{node.source_ref.path}`")
    # code open
    paths = list(node.properties.get("paths") or [])
    if node.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
        abs_p = node.properties.get("absolute_path")
        rel = node.properties.get("path")
        if abs_p and node.properties.get("exists"):
            lines.append(f"- VS Code: {file_open_link(abs_p, label=str(rel), vscode_enabled=config.vscode_enabled)}")
    elif paths:
        for p in paths[:5]:
            abs_p = (config.repo_root / p).resolve()
            if abs_p.exists():
                lines.append(
                    f"- VS Code: {file_open_link(abs_p, label=p, vscode_enabled=config.vscode_enabled)}"
                )
    lines.append("- Canvas: [[Canvas/Requirement-Traceability.canvas|Трассируемость (canvas)]]")
    lines.append("")
    return lines


def _classification_table(node: Node, graph: AtlasGraph) -> list[str]:
    props = node.properties
    rows = [
        ("Тип", props.get("grace_type") or node.type),
        ("Статус", node.status or "unknown"),
        ("Приоритет", props.get("priority") or "—"),
        ("Тип требования", props.get("requirement_type") or "—"),
        ("Состояние источника", props.get("source_state") or "—"),
        ("Источник", props.get("source_file") or (node.source_ref.path if node.source_ref else "—")),
    ]
    if props.get("source_line") or (node.source_ref and node.source_ref.line_start):
        rows.append(("Строка", str(props.get("source_line") or node.source_ref.line_start)))
    lines = ["## Классификация", "", "| Поле | Значение |", "|---|---|"]
    for k, v in rows:
        lines.append(f"| {k} | {v} |")
    lines.append("")
    return lines


def _link_list_section(title: str, items: list[str] | None) -> list[str]:
    if not items:
        return [f"### {title}", "", "- _отсутствует / не declared_", ""]
    lines = [f"### {title}", ""]
    for it in items:
        # already wiki links in properties
        if it.startswith("[["):
            lines.append(f"- {it}")
        else:
            lines.append(f"- `{it}`")
    lines.append("")
    return lines


def render_node_note(node: Node, graph: AtlasGraph, config: AtlasConfig) -> str:
    props = node.properties or {}
    display = props.get("display_name") or node.name or node.id
    lines: list[str] = [
        GENERATED_BANNER,
        "",
        render_frontmatter(node),
        "",
        f"# {node.id} — {display}",
        "",
        HUMAN_BANNER,
        "",
        "## Формулировка",
        "",
        node.description or "_(нет описания в GRACE)_",
        "",
    ]
    lines.extend(_classification_table(node, graph))

    # Traceability-focused sections for human scan
    if node.type in {
        NodeType.USE_CASE,
        NodeType.REQUIREMENT,
        NodeType.CONSTRAINT,
        NodeType.RISK,
        NodeType.NON_GOAL,
    }:
        lines.append("## Трассировка")
        lines.append("")
        lines.extend(_link_list_section("Пользовательские сценарии / related", props.get("belongs_to_use_case")))
        lines.extend(_link_list_section("Реализующие модули", props.get("implemented_by") or props.get("implements")))
        lines.extend(_link_list_section("Исходные файлы", props.get("implemented_in")))
        lines.extend(_link_list_section("Verification", props.get("verified_by")))
        lines.extend(_link_list_section("Тесты", props.get("tested_by")))
        lines.extend(_link_list_section("Evidence", props.get("evidence")))
        lines.extend(_link_list_section("Фазы / plan", props.get("planned_in")))

    if node.type == NodeType.MODULE:
        lines.append("## Трассировка модуля")
        lines.append("")
        lines.extend(_link_list_section("Реализует (implements)", props.get("implements")))
        lines.extend(_link_list_section("Зависит от", props.get("depends_on")))
        lines.extend(_link_list_section("Зависят от этого", props.get("dependency_of")))
        lines.extend(_link_list_section("Исходные файлы", props.get("implemented_in")))
        lines.extend(_link_list_section("Verification", props.get("verified_by")))
        lines.extend(_link_list_section("Тесты", props.get("tested_by")))
        lines.extend(_link_list_section("Контракты", props.get("contracts")))
        lines.extend(_link_list_section("Семантические блоки", props.get("semantic_blocks")))

    if node.type == NodeType.VERIFICATION:
        lines.append("## Verification")
        lines.append("")
        lines.extend(_link_list_section("Проверяет (модули)", props.get("verifies")))
        tf = props.get("test_files") or []
        lines.extend(_link_list_section("Test files", [f"`{t}`" for t in tf] if tf else None))
        lines.extend(_link_list_section("Commands / checks", props.get("commands") or props.get("checks")))
        lines.extend(_link_list_section("Evidence", props.get("evidence")))
        lines.append(f"- last_known_result: `{props.get('last_known_result') or node.status}`")
        lines.append("")

    if node.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
        lines.append("## Файл")
        lines.append("")
        lines.append(f"- path: `{props.get('path') or node.name}`")
        lines.append(f"- exists: `{props.get('exists')}`")
        lines.append("")
        lines.extend(_link_list_section("Модули (implemented_in reverse)", props.get("implemented_by")))
        # also show incoming via edge sections below

    lines.extend(_problems_section(node))

    # Full edge materialization for Local Graph
    lines.append("## Связи (wiki-links для Local Graph)")
    lines.append("")
    out_sec = _edge_sections(graph, node, outgoing=True)
    in_sec = _edge_sections(graph, node, outgoing=False)
    if out_sec or in_sec:
        lines.extend(out_sec)
        lines.extend(in_sec)
    else:
        lines.append("_Нет рёбер (orphan)._")
        lines.append("")

    lines.extend(_nav_section(node, config))
    lines.append("---")
    lines.append("_GRACE Atlas workbench · read-only · `generated: true`_")
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
        f"Всего: **{len(nodes_list)}**",
        "",
        "> Индексные страницы: исключите тег `grace/index` из Graph View.",
        "",
        "Workbench: [[Dashboards/Workbench]] · Base: [[Views/Requirements.base]]",
        "",
    ]
    for n in nodes_list:
        status = f" `{n.status}`" if n.status else ""
        gap = " ⚠" if n.properties.get("has_traceability_gap") else ""
        lines.append(f"- {wikilink(n, n.id)}{status}{gap}")
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
        f"Сгенерировано: **{generated_at}** (UTC)",
        "",
        "Проекция только для чтения. **Старт для человека:** [[Dashboards/Workbench]].",
        "",
        "## Workbench (основной UI)",
        "",
        "- [[Dashboards/Workbench|Домашняя страница Workbench]]",
        "- [[Views/Requirements.base|Реестр требований]]",
        "- [[Dashboards/Requirement-Tree|Дерево требований / UC]]",
        "- [[Dashboards/Traceability-Matrix|Матрица трассируемости]]",
        "- [[Dashboards/User-Journey-Video2PPTX|Пользовательский сценарий]]",
        "- [[Dashboards/How-to-use|Как пользоваться]]",
        "",
        "## Canvas (дополнительно)",
        "",
        "- [[Canvas/Project-Overview.canvas|Обзор проекта]]",
        "- [[Canvas/Current-Phase.canvas|Текущая фаза]]",
        "- [[Canvas/User-Journey.canvas|User Journey]]",
        "- [[Canvas/Requirement-Traceability.canvas|Трассируемость требований]]",
        "- [[Canvas/Verification-Gaps.canvas|Пробелы верификации]]",
        "",
        "## Диагностика",
        "",
        "- [[Diagnostics/Summary|Сводка]]",
        "- [[Diagnostics/Gaps-Registry|Реестр gaps]]",
        "- [[Diagnostics/Broken-References|Битые ссылки]]",
        "- [[Diagnostics/Orphan-Requirements|Сироты требований]]",
        "- [[Diagnostics/Unverified-Modules|Непроверенные модули]]",
        "",
        "## Статистика",
        "",
        f"- Узлы: **{stats['nodes']}** · Рёбра: **{stats['edges']}**",
        f"- Gaps: **{gap_summary.get('findings', 0)}** `{gap_summary.get('by_severity', {})}`",
        "",
        "### Артефакты GRACE (пути, без изменения XML)",
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
    lines.extend(
        [
            "",
            "## Пересборка",
            "",
            "```powershell",
            "python tools/grace_atlas.py build --project-root .",
            "```",
            "",
            "---",
            "_Home **не** ссылается на каждую сущность (чтобы не получить star-graph)._",
            "",
        ]
    )
    return "\n".join(lines)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "TYPE_FOLDERS",
    "GENERATED_BANNER",
    "note_relpath",
    "render_node_note",
    "render_index",
    "render_home",
    "utc_now_iso",
    "render_frontmatter",
]

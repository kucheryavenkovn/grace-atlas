# FILE: tools/grace_atlas/src/grace_atlas/exporters/canvas.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Deterministic JSON Canvas exporters for five required Atlas scenarios.
#   SCOPE: Project-Overview, Current-Phase, User-Journey, Requirement-Traceability, Verification-Gaps
#   DEPENDS: exporters.notes, model, diagnostics
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Obsidian JSON Canvas generators (deterministic layout, file cards)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from grace_atlas.diagnostics import GapReport
from grace_atlas.exporters.notes import note_relpath
from grace_atlas.model import AtlasGraph, EdgeType, Node, NodeType

# JSON Canvas color categories (Obsidian palette indices as strings)
COLOR = {
    "requirement": "1",  # red
    "module": "4",  # green
    "file": "5",  # cyan
    "verification": "6",  # purple
    "test": "3",  # yellow
    "phase": "2",  # orange
    "gap": "1",
    "meta": "0",
}


def _stable_id(*parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def _file_node(node: Node, x: int, y: int, w: int = 300, h: int = 220, color: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": _stable_id("file", node.id),
        "type": "file",
        "file": note_relpath(node).replace("\\", "/"),
        "x": x,
        "y": y,
        "width": w,
        "height": h,
    }
    if color:
        d["color"] = color
    return d


def _text_node(key: str, text: str, x: int, y: int, w: int = 280, h: int = 100, color: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": _stable_id("text", key),
        "type": "text",
        "text": text,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
    }
    if color:
        d["color"] = color
    return d


def _edge(from_id: str, to_id: str, label: str = "", *, key: str = "") -> dict[str, Any]:
    e: dict[str, Any] = {
        "id": _stable_id("edge", key or f"{from_id}->{to_id}:{label}"),
        "fromNode": from_id,
        "fromSide": "right",
        "toNode": to_id,
        "toSide": "left",
        "toEnd": "arrow",
    }
    if label:
        e["label"] = label
    return e


def _pick(graph: AtlasGraph, ntype: str, limit: int = 12) -> list[Node]:
    nodes = graph.nodes_by_type(ntype)

    def score(n: Node) -> tuple:
        stub = 1 if n.properties.get("stub") else 0
        status = (n.status or "").lower()
        prefer = 0 if status in {"implemented", "passed", "done", "in_progress"} else 1
        return (stub, prefer, n.id)

    return sorted(nodes, key=score)[:limit]


def canvas_project_overview(graph: AtlasGraph) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    title = _text_node(
        "overview-title",
        f"# Project Overview\n\n{graph.meta.get('project_name', 'Project')}\n"
        f"modules={len(graph.nodes_by_type(NodeType.MODULE))} "
        f"UC={len(graph.nodes_by_type(NodeType.USE_CASE))} "
        f"V={len(graph.nodes_by_type(NodeType.VERIFICATION))}",
        x=0,
        y=-220,
        w=420,
        h=120,
        color=COLOR["meta"],
    )
    nodes.append(title)

    # Subsystem hubs by module TYPE property when available
    core_ids = [
        "M-CLI",
        "M-DETECT-SLIDES",
        "M-SLIDE-DETECTOR",
        "M-APP-DETECT",
        "M-APP-AUTO",
        "M-APP-EXPORT",
        "M-DOMAIN-PROJECT",
        "M-FILE-REPO",
        "M-GUI-MAIN",
        "M-PROJECT",
        "M-SUBTITLES",
        "M-MD-EXPORT",
        "M-PPTX-EXPORT",
        "M-MODELS",
        "M-CONFIG",
    ]
    selected: list[Node] = []
    for mid in core_ids:
        n = graph.get(mid)
        if n:
            selected.append(n)
    if len(selected) < 8:
        selected = _pick(graph, NodeType.MODULE, 12)

    id_map: dict[str, str] = {}
    cols = 4
    for i, mod in enumerate(selected):
        x = (i % cols) * 360
        y = (i // cols) * 280
        fn = _file_node(mod, x=x, y=y, color=COLOR["module"])
        nodes.append(fn)
        id_map[mod.id] = fn["id"]
        edges.append(_edge(title["id"], fn["id"], key=f"title-{mod.id}"))

    for e in graph.edges:
        if e.type != EdgeType.DEPENDS_ON:
            continue
        if e.source in id_map and e.target in id_map:
            edges.append(_edge(id_map[e.source], id_map[e.target], "depends_on", key=f"dep-{e.source}-{e.target}"))

    # Sample UC + verification hubs
    for i, uc in enumerate(_pick(graph, NodeType.USE_CASE, 6)):
        fn = _file_node(uc, x=-500, y=i * 240, w=280, h=180, color=COLOR["requirement"])
        nodes.append(fn)
    for i, v in enumerate(_pick(graph, NodeType.VERIFICATION, 6)):
        fn = _file_node(v, x=1600, y=i * 240, w=280, h=180, color=COLOR["verification"])
        nodes.append(fn)

    return {"nodes": nodes, "edges": edges}


def _detect_current_phase(graph: AtlasGraph) -> Node | None:
    phases = graph.nodes_by_type(NodeType.PHASE)
    # Prefer in_progress, then last non-done with activity
    in_prog = [p for p in phases if (p.status or "").lower() in {"in_progress", "in-progress", "active"}]
    if in_prog:
        return sorted(in_prog, key=lambda p: p.id)[-1]
    # Heuristic: highest Phase number that is not done
    open_phases = [p for p in phases if (p.status or "").lower() not in {"done", "completed", "passed"}]
    if open_phases:
        return sorted(open_phases, key=_phase_key)[-1]
    if phases:
        return sorted(phases, key=_phase_key)[-1]
    return None


def _phase_key(p: Node) -> tuple:
    try:
        return (int(p.id.split("-", 1)[1]),)
    except (IndexError, ValueError):
        return (9999, p.id)


def canvas_current_phase(graph: AtlasGraph) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    phase = _detect_current_phase(graph)
    if phase is None:
        nodes.append(
            _text_node(
                "no-phase",
                "# Current Phase\n\nCannot determine current phase from GRACE data "
                "(no Phase-* nodes with status).",
                x=0,
                y=0,
                w=480,
                h=160,
                color=COLOR["gap"],
            )
        )
        return {"nodes": nodes, "edges": edges}

    p_node = _file_node(phase, x=400, y=0, w=360, h=240, color=COLOR["phase"])
    nodes.append(p_node)
    nodes.append(
        _text_node(
            "phase-header",
            f"# Current Phase\n\nDetected from status=`{phase.status}`\n`{phase.id}`",
            x=0,
            y=-200,
            w=360,
            h=120,
            color=COLOR["meta"],
        )
    )
    edges.append(_edge(nodes[-1]["id"], p_node["id"], key="hdr-phase"))

    # Steps of phase
    step_nodes: list[Node] = []
    for e in graph.edges:
        if e.source == phase.id and e.type == EdgeType.CONTAINS:
            st = graph.get(e.target)
            if st and st.type == NodeType.STEP:
                step_nodes.append(st)
    step_nodes = sorted(step_nodes, key=lambda n: n.id)[:12]
    step_ids: dict[str, str] = {}
    for i, st in enumerate(step_nodes):
        fn = _file_node(st, x=(i % 4) * 340, y=320 + (i // 4) * 240, w=300, h=200, color=COLOR["phase"])
        nodes.append(fn)
        step_ids[st.id] = fn["id"]
        edges.append(_edge(p_node["id"], fn["id"], "contains", key=f"ph-st-{st.id}"))

    # Verification from steps
    ver_y = 900
    seen_v: set[str] = set()
    for st in step_nodes:
        for e in graph.edges:
            if e.source == st.id and e.type == EdgeType.VERIFIED_BY and e.target not in seen_v:
                seen_v.add(e.target)
                v = graph.get(e.target)
                if not v:
                    continue
                fn = _file_node(v, x=len(seen_v) * 320, y=ver_y, w=280, h=180, color=COLOR["verification"])
                nodes.append(fn)
                edges.append(_edge(step_ids[st.id], fn["id"], "verified_by", key=f"st-v-{st.id}-{v.id}"))
                if len(seen_v) >= 10:
                    break
        if len(seen_v) >= 10:
            break

    # Operational packets (usually templates)
    for i, pk in enumerate(_pick(graph, NodeType.OPERATIONAL_PACKET, 4)):
        fn = _file_node(pk, x=-400, y=i * 220, w=300, h=180, color=COLOR["meta"])
        nodes.append(fn)

    # Blocked verifications as blockers
    blocked = [
        n
        for n in graph.nodes_by_type(NodeType.VERIFICATION)
        if (n.status or "").lower() == "blocked"
    ][:6]
    for i, b in enumerate(sorted(blocked, key=lambda n: n.id)):
        fn = _file_node(b, x=1400, y=i * 220, w=300, h=180, color=COLOR["gap"])
        nodes.append(fn)

    return {"nodes": nodes, "edges": edges}


# User-journey stages mapped to real UC ids when present (gaps otherwise)
JOURNEY_STAGES: list[tuple[str, list[str], list[str]]] = [
    # (label, preferred UC ids, preferred module ids)
    ("Установка", [], ["M-CLI", "M-DESKTOP-BOOTSTRAP", "DS-GUI"]),
    ("Запуск", ["UC-013"], ["M-CLI", "M-GUI-MAIN"]),
    ("Создание проекта", ["UC-008"], ["M-PROJECT", "M-APP-PROJECT", "M-DOMAIN-PROJECT"]),
    ("Загрузка видео", ["UC-013", "UC-008"], ["M-PROJECT", "M-GUI-MAIN"]),
    ("Загрузка субтитров", ["UC-013", "UC-006"], ["M-SUBTITLES", "M-PROJECT"]),
    ("Auto", ["UC-009"], ["M-APP-AUTO", "M-AUTO-ALIGN"]),
    ("Detect", ["UC-001", "UC-005", "UC-009"], ["M-DETECT-SLIDES", "M-APP-DETECT", "M-SLIDE-DETECTOR"]),
    ("Формирование PPTX", ["UC-002"], ["M-PPTX-EXPORT", "M-APP-EXPORT", "M-MD-EXPORT"]),
    ("Сохранение", ["UC-008", "UC-013"], ["M-PROJECT", "M-FILE-REPO", "M-ATOMIC-JSON"]),
    ("Закрытие", ["UC-013"], ["M-GUI-MAIN", "M-PROJECT-MODEL"]),
    ("Повторное открытие", ["UC-008", "UC-013"], ["M-PROJECT", "M-FILE-REPO", "M-APP-PROJECT"]),
    ("Сохранность состояния", ["UC-008", "UC-010"], ["M-DOMAIN-STATE", "M-FILE-REPO", "M-PROJECT"]),
]


def canvas_user_journey(graph: AtlasGraph) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    header = _text_node(
        "journey-header",
        "# User Journey\n\nBased only on real UC/modules found in GRACE.\n"
        "Steps without evidence are marked as **gap**.",
        x=0,
        y=-200,
        w=480,
        h=120,
        color=COLOR["meta"],
    )
    nodes.append(header)

    prev_id: str | None = None
    for i, (label, uc_ids, mod_ids) in enumerate(JOURNEY_STAGES):
        y = i * 280
        uc_node = None
        for uid in uc_ids:
            uc_node = graph.get(uid)
            if uc_node:
                break
        mod_node = None
        for mid in mod_ids:
            mod_node = graph.get(mid)
            if mod_node and not mod_node.properties.get("stub"):
                break
        if mod_node is None:
            for mid in mod_ids:
                mod_node = graph.get(mid)
                if mod_node:
                    break

        stage = _text_node(
            f"stage-{i}-{label}",
            f"## {i + 1}. {label}\n\n"
            + (f"UC: `{uc_node.id}`" if uc_node else "**gap**: no matching UC in requirements")
            + "\n"
            + (f"Module: `{mod_node.id}`" if mod_node else "**gap**: no matching module"),
            x=0,
            y=y,
            w=320,
            h=140,
            color=COLOR["gap"] if not uc_node and not mod_node else COLOR["meta"],
        )
        nodes.append(stage)
        if prev_id:
            edges.append(_edge(prev_id, stage["id"], "next", key=f"journey-{i}"))
        prev_id = stage["id"]

        col = 400
        if uc_node:
            fn = _file_node(uc_node, x=col, y=y, w=280, h=160, color=COLOR["requirement"])
            nodes.append(fn)
            edges.append(_edge(stage["id"], fn["id"], "requirement", key=f"j-uc-{i}"))
            col += 340
        if mod_node:
            fn = _file_node(mod_node, x=col, y=y, w=280, h=160, color=COLOR["module"])
            nodes.append(fn)
            edges.append(_edge(stage["id"], fn["id"], "module", key=f"j-mod-{i}"))
            # verification + files
            v_edge = next((e for e in graph.edges if e.source == mod_node.id and e.type == EdgeType.VERIFIED_BY), None)
            if v_edge:
                v = graph.get(v_edge.target)
                if v:
                    vf = _file_node(v, x=col + 340, y=y, w=260, h=160, color=COLOR["verification"])
                    nodes.append(vf)
                    edges.append(_edge(fn["id"], vf["id"], "verified_by", key=f"j-v-{i}"))
                    status = v.status or "?"
                    evidence = "has evidence" if (v.properties.get("evidence_count") or 0) > 0 else "no evidence node"
                    # tests
                    t_edge = next((e for e in graph.edges if e.source == v.id and e.type == EdgeType.TESTED_BY), None)
                    if t_edge:
                        t = graph.get(t_edge.target)
                        if t:
                            tf = _file_node(t, x=col + 680, y=y, w=260, h=160, color=COLOR["test"])
                            nodes.append(tf)
                            edges.append(_edge(vf["id"], tf["id"], f"tested_by ({status})", key=f"j-t-{i}"))
                    else:
                        gap = _text_node(
                            f"j-gap-t-{i}",
                            f"gap: no tests\nstatus={status}\n{evidence}",
                            x=col + 680,
                            y=y,
                            w=220,
                            h=120,
                            color=COLOR["gap"],
                        )
                        nodes.append(gap)
            f_edge = next((e for e in graph.edges if e.source == mod_node.id and e.type == EdgeType.IMPLEMENTED_IN), None)
            if f_edge:
                f = graph.get(f_edge.target)
                if f:
                    ff = _file_node(f, x=col, y=y + 180, w=260, h=120, color=COLOR["file"])
                    nodes.append(ff)
                    edges.append(_edge(fn["id"], ff["id"], "implemented_in", key=f"j-f-{i}"))

    return {"nodes": nodes, "edges": edges}


def canvas_requirement_traceability(graph: AtlasGraph) -> dict[str, Any]:
    """Columns: UC | Module | File | Verification | Test | Evidence"""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    col_x = {
        "uc": 0,
        "mod": 400,
        "file": 800,
        "ver": 1200,
        "test": 1600,
        "ev": 2000,
    }
    headers = [
        ("h-uc", "Requirements / UC", col_x["uc"]),
        ("h-mod", "Modules", col_x["mod"]),
        ("h-file", "Source Files", col_x["file"]),
        ("h-ver", "Verification", col_x["ver"]),
        ("h-test", "Tests", col_x["test"]),
        ("h-ev", "Evidence", col_x["ev"]),
    ]
    for key, title, x in headers:
        nodes.append(_text_node(key, f"**{title}**", x=x, y=-140, w=280, h=60, color=COLOR["meta"]))

    # Build chains from use cases with related flows / VF
    use_cases = _pick(graph, NodeType.USE_CASE, 10)
    # Also include modules that have full chain
    row = 0
    max_rows = 14
    for uc in use_cases:
        if row >= max_rows:
            break
        y = row * 260
        uc_fn = _file_node(uc, x=col_x["uc"], y=y, w=280, h=180, color=COLOR["requirement"])
        nodes.append(uc_fn)

        # Find modules via VF that uses this UC, then MODULE attribute — or via related flows only
        modules: list[Node] = []
        for e in graph.edges:
            if e.target == uc.id and e.type == EdgeType.USES_USE_CASE:
                # VF — no direct module; skip to show flow
                pass
        # Prefer modules mentioned in UC-related DF is weak; use high-priority modules by keyword
        # Fall back: for each UC show linked DF only
        related = [e for e in graph.edges if e.source == uc.id and e.type == EdgeType.RELATED_FLOW]
        # Try to attach a representative module from verification of similar name — skip heuristics that invent
        # Instead: pick modules that have implemented_in + verified_by for a parallel chain under UC row
        if not modules:
            # Place DF as intermediate note
            for e in related[:1]:
                df = graph.get(e.target)
                if df:
                    dfn = _file_node(df, x=col_x["mod"] - 50, y=y, w=260, h=160, color=COLOR["meta"])
                    nodes.append(dfn)
                    edges.append(_edge(uc_fn["id"], dfn["id"], "related_flow", key=f"uc-df-{uc.id}-{df.id}"))

        # Full chains from modules (shared rows after UCs)
        row += 1

    # Dedicated module chains (most valuable for columns)
    chain_mods = _pick(graph, NodeType.MODULE, 12)
    for mod in chain_mods:
        if row >= max_rows + 12:
            break
        if mod.properties.get("stub"):
            continue
        y = row * 260
        m_fn = _file_node(mod, x=col_x["mod"], y=y, w=280, h=180, color=COLOR["module"])
        nodes.append(m_fn)

        # file
        f_edge = next((e for e in graph.edges if e.source == mod.id and e.type == EdgeType.IMPLEMENTED_IN), None)
        if f_edge:
            f = graph.get(f_edge.target)
            if f:
                f_fn = _file_node(f, x=col_x["file"], y=y, w=280, h=160, color=COLOR["file"])
                nodes.append(f_fn)
                edges.append(_edge(m_fn["id"], f_fn["id"], "implemented_in", key=f"tr-f-{mod.id}"))

        v_edge = next((e for e in graph.edges if e.source == mod.id and e.type == EdgeType.VERIFIED_BY), None)
        if v_edge:
            v = graph.get(v_edge.target)
            if v:
                v_fn = _file_node(v, x=col_x["ver"], y=y, w=280, h=160, color=COLOR["verification"])
                nodes.append(v_fn)
                edges.append(_edge(m_fn["id"], v_fn["id"], "verified_by", key=f"tr-v-{mod.id}"))
                t_edge = next((e for e in graph.edges if e.source == v.id and e.type == EdgeType.TESTED_BY), None)
                if t_edge:
                    t = graph.get(t_edge.target)
                    if t:
                        t_fn = _file_node(t, x=col_x["test"], y=y, w=280, h=160, color=COLOR["test"])
                        nodes.append(t_fn)
                        edges.append(_edge(v_fn["id"], t_fn["id"], "tested_by", key=f"tr-t-{mod.id}"))
                ev_edge = next((e for e in graph.edges if e.source == v.id and e.type == EdgeType.PRODUCES_EVIDENCE), None)
                if ev_edge:
                    ev = graph.get(ev_edge.target)
                    if ev:
                        ev_fn = _file_node(ev, x=col_x["ev"], y=y, w=260, h=140, color=COLOR["meta"])
                        nodes.append(ev_fn)
                        edges.append(_edge(v_fn["id"], ev_fn["id"], "evidence", key=f"tr-e-{mod.id}"))
        row += 1

    return {"nodes": nodes, "edges": edges}


def canvas_verification_gaps(graph: AtlasGraph, report: GapReport) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    header = _text_node(
        "gaps-header",
        f"# Verification Gaps\n\nfindings={report.summary.get('findings')}\n"
        f"broken={report.summary.get('broken_references')} "
        f"unverified={report.summary.get('unverified_modules')} "
        f"unmapped={report.summary.get('unmapped_files')}",
        x=0,
        y=-200,
        w=480,
        h=140,
        color=COLOR["gap"],
    )
    nodes.append(header)

    groups = [
        ("UNVERIFIED_MODULE", 0, "Unverified modules"),
        ("MISSING_FILE", 500, "Missing files"),
        ("ORPHAN_REQUIREMENT", 1000, "Orphan UC/requirements"),
        ("UNMAPPED_FILE", 1500, "Unmapped files"),
        ("BROKEN_REFERENCE", 2000, "Broken references"),
    ]
    for code, x, title in groups:
        hub = _text_node(f"gap-hub-{code}", f"**{title}**", x=x, y=0, w=280, h=70, color=COLOR["gap"])
        nodes.append(hub)
        edges.append(_edge(header["id"], hub["id"], key=f"hdr-{code}"))
        items = report.by_code(code)[:8]
        for i, f in enumerate(items):
            n = graph.get(f.entity_id)
            y = 120 + i * 220
            if n:
                fn = _file_node(n, x=x, y=y, w=280, h=180, color=COLOR["gap"])
                nodes.append(fn)
                edges.append(_edge(hub["id"], fn["id"], code, key=f"gap-{code}-{f.entity_id}-{i}"))
            else:
                tn = _text_node(
                    f"gap-txt-{code}-{i}-{f.entity_id}",
                    f"`{f.entity_id}`\n{f.message[:120]}",
                    x=x,
                    y=y,
                    w=280,
                    h=120,
                    color=COLOR["gap"],
                )
                nodes.append(tn)
                edges.append(_edge(hub["id"], tn["id"], code, key=f"gap-t-{code}-{i}"))

    return {"nodes": nodes, "edges": edges}


def dumps_canvas(data: dict[str, Any]) -> str:
    # Deterministic JSON: sort keys, stable structure already from stable ids
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def validate_canvas_file_refs(data: dict[str, Any], existing_notes: set[str]) -> list[str]:
    """Return list of missing note paths referenced by canvas file nodes."""
    missing: list[str] = []
    for n in data.get("nodes") or []:
        if n.get("type") == "file":
            f = str(n.get("file") or "").replace("\\", "/")
            if f and f not in existing_notes:
                missing.append(f)
    return missing


def build_all_canvases(graph: AtlasGraph, report: GapReport) -> dict[str, str]:
    canvases = {
        "Canvas/Project-Overview.canvas": canvas_project_overview(graph),
        "Canvas/Current-Phase.canvas": canvas_current_phase(graph),
        "Canvas/User-Journey.canvas": canvas_user_journey(graph),
        "Canvas/Requirement-Traceability.canvas": canvas_requirement_traceability(graph),
        "Canvas/Verification-Gaps.canvas": canvas_verification_gaps(graph, report),
    }
    return {path: dumps_canvas(data) for path, data in canvases.items()}

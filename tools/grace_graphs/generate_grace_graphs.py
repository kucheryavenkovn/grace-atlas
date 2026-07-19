#!/usr/bin/env python3
# FILE: tools/grace_graphs/generate_grace_graphs.py
# VERSION: 0.1.0
# PURPOSE: Standalone (stdlib-only) Graphviz + Mermaid graphs from GRACE docs/*.xml
#
# Does NOT depend on grace-atlas. Reads only docs XML under project root.
#
# Usage:
#   python tools/grace_graphs/generate_grace_graphs.py --project-root .
#   python tools/grace_graphs/generate_grace_graphs.py --project-root . --out docs/grace-graphs
#   python tools/grace_graphs/generate_grace_graphs.py --list
#   python tools/grace_graphs/generate_grace_graphs.py --only modules-deps,phases

"""Generate Graphviz DOT and Mermaid diagrams from GRACE XML artifacts in docs/."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Graph:
    """Simple directed graph for export."""

    title: str
    nodes: dict[str, str] = field(default_factory=dict)  # id -> label
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # src, dst, label
    node_groups: dict[str, list[str]] = field(default_factory=dict)  # group -> ids

    def add_node(self, node_id: str, label: str | None = None) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = label or node_id
        elif label and (not self.nodes[node_id] or self.nodes[node_id] == node_id):
            self.nodes[node_id] = label

    def add_edge(self, src: str, dst: str, label: str = "") -> None:
        self.add_node(src)
        self.add_node(dst)
        key = (src, dst, label)
        if key not in self.edges:
            self.edges.append(key)

    def add_to_group(self, group: str, node_id: str) -> None:
        self.node_groups.setdefault(group, [])
        if node_id not in self.node_groups[group]:
            self.node_groups[group].append(node_id)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def child_text(el: ET.Element, *names: str) -> str:
    want = set(names)
    for c in el:
        if local(c.tag) in want:
            t = text(c)
            if t:
                return t
    return ""


def attr(el: ET.Element, *names: str, default: str = "") -> str:
    for n in names:
        if n in el.attrib:
            return str(el.attrib[n]).strip()
    lower = {k.lower(): v for k, v in el.attrib.items()}
    for n in names:
        if n.lower() in lower:
            return str(lower[n.lower()]).strip()
    return default


def split_ids(raw: str) -> list[str]:
    if not raw or raw.strip().lower() in {"none", "n/a", "-", ""}:
        return []
    parts = re.split(r"[,;|/]+", raw)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # keep module-like and free tokens that look like IDs
        if re.match(r"^[A-Za-z][A-Za-z0-9._-]*$", p):
            out.append(p)
    return out


def load_xml(path: Path) -> ET.Element | None:
    if not path.is_file():
        return None
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        print(f"WARN: failed to parse {path}: {exc}", file=sys.stderr)
        return None


def find_docs(project_root: Path) -> dict[str, Path]:
    """Locate GRACE XML under docs/ or project root (fixtures often use root)."""
    names = {
        "requirements": "requirements.xml",
        "development_plan": "development-plan.xml",
        "knowledge_graph": "knowledge-graph.xml",
        "verification_plan": "verification-plan.xml",
        "technology": "technology.xml",
        "operational_packets": "operational-packets.xml",
    }
    mapping: dict[str, Path] = {}
    for key, fname in names.items():
        found: Path | None = None
        for base in (project_root / "docs", project_root):
            candidate = base / fname
            if candidate.is_file():
                found = candidate
                break
        mapping[key] = found if found is not None else (project_root / "docs" / fname)
    return mapping


# ---------------------------------------------------------------------------
# Parsers → intermediate records
# ---------------------------------------------------------------------------


@dataclass
class GraceData:
    modules: dict[str, dict] = field(default_factory=dict)  # id -> meta
    depends: list[tuple[str, str]] = field(default_factory=list)
    cross_links: list[tuple[str, str, str]] = field(default_factory=list)
    verifications: dict[str, dict] = field(default_factory=dict)
    use_cases: dict[str, dict] = field(default_factory=dict)
    data_flows: dict[str, dict] = field(default_factory=dict)
    critical_flows: dict[str, dict] = field(default_factory=dict)
    phases: dict[str, dict] = field(default_factory=dict)
    steps: dict[str, dict] = field(default_factory=dict)  # step -> phase, verification


def parse_knowledge_graph(root: ET.Element, data: GraceData) -> None:
    project = root
    for c in root:
        if local(c.tag) == "Project":
            project = c
            break
    for el in project:
        tag = local(el.tag)
        if tag == "CrossLink":
            src = attr(el, "from", "FROM")
            dst = attr(el, "to", "TO")
            rel = attr(el, "relation", "RELATION", default="cross_link")
            if src and dst:
                data.cross_links.append((src, dst, rel))
            continue
        if not tag.startswith("M-"):
            continue
        name = attr(el, "NAME", "name", default=tag)
        status = attr(el, "STATUS", "status")
        mtype = attr(el, "TYPE", "type")
        purpose = child_text(el, "purpose", "PURPOSE")
        vref = child_text(el, "verification-ref", "verification_ref")
        deps_raw = child_text(el, "depends", "DEPENDS")
        paths = [text(c) for c in el if local(c.tag) == "path" and text(c)]
        data.modules[tag] = {
            "name": name,
            "status": status,
            "type": mtype,
            "purpose": purpose,
            "verification": vref,
            "paths": paths,
            "source": "knowledge-graph",
        }
        for dep in split_ids(deps_raw):
            if dep.startswith("M-"):
                data.depends.append((tag, dep))
        # nested submodules
        for sub in el.iter():
            st = local(sub.tag)
            if sub is el or not st.startswith("M-"):
                continue
            sname = attr(sub, "NAME", "name", default=st)
            data.modules.setdefault(
                st,
                {
                    "name": sname,
                    "status": attr(sub, "STATUS", "status"),
                    "type": "submodule",
                    "purpose": attr(sub, "PURPOSE", default=""),
                    "verification": "",
                    "paths": [],
                    "source": "knowledge-graph",
                },
            )
            data.depends.append((tag, st))


def parse_development_plan(root: ET.Element, data: GraceData) -> None:
    for section in root:
        stag = local(section.tag)
        if stag == "Modules":
            for el in section:
                tag = local(el.tag)
                if not tag.startswith("M-"):
                    continue
                name = attr(el, "NAME", "name", default=tag)
                status = attr(el, "STATUS", "status")
                mtype = attr(el, "TYPE", "type")
                purpose = ""
                for c in el:
                    if local(c.tag) == "contract":
                        purpose = child_text(c, "purpose", "PURPOSE") or purpose
                vref = child_text(el, "verification-ref")
                deps_raw = child_text(el, "depends", "DEPENDS")
                existing = data.modules.get(tag, {})
                data.modules[tag] = {
                    **existing,
                    "name": name or existing.get("name", tag),
                    "status": status or existing.get("status", ""),
                    "type": mtype or existing.get("type", ""),
                    "purpose": purpose or existing.get("purpose", ""),
                    "verification": vref or existing.get("verification", ""),
                    "source": existing.get("source", "development-plan"),
                }
                for dep in split_ids(deps_raw):
                    if dep.startswith("M-") and (tag, dep) not in data.depends:
                        data.depends.append((tag, dep))
        elif stag == "DataFlow":
            for el in section:
                tag = local(el.tag)
                if tag.startswith("DF-"):
                    data.data_flows[tag] = {
                        "name": attr(el, "NAME", "name", default=tag),
                        "trigger": attr(el, "TRIGGER", "trigger"),
                    }
        elif stag == "ImplementationOrder":
            for phase in section:
                ptag = local(phase.tag)
                if not ptag.startswith("Phase-"):
                    continue
                data.phases[ptag] = {
                    "name": attr(phase, "name", "NAME", default=ptag),
                    "status": attr(phase, "status", "STATUS"),
                    "goal": child_text(phase, "goal", "GOAL"),
                }
                for step in phase:
                    stag2 = local(step.tag)
                    if not stag2.startswith("step-"):
                        continue
                    data.steps[stag2] = {
                        "name": attr(step, "name", "NAME", default=stag2),
                        "status": attr(step, "status", "STATUS"),
                        "phase": ptag,
                        "verification": attr(step, "verification", "VERIFICATION"),
                    }


def parse_requirements(root: ET.Element, data: GraceData) -> None:
    for section in root:
        if local(section.tag) != "UseCases":
            continue
        for el in section:
            tag = local(el.tag)
            if not tag.startswith("UC-"):
                continue
            action = child_text(el, "Action", "action")
            goal = child_text(el, "Goal", "goal")
            flows = child_text(el, "RelatedFlows", "related-flows")
            data.use_cases[tag] = {
                "name": action or goal or tag,
                "goal": goal,
                "flows": split_ids(flows),
                "priority": child_text(el, "Priority", "priority"),
            }


def parse_verification(root: ET.Element, data: GraceData) -> None:
    for section in root:
        stag = local(section.tag)
        if stag == "CriticalFlows":
            for el in section:
                tag = local(el.tag)
                if not tag.startswith("VF-"):
                    continue
                data.critical_flows[tag] = {
                    "name": attr(el, "NAME", "name", default=tag),
                    "use_cases": split_ids(attr(el, "USE_CASES", "use_cases")),
                    "data_flow": split_ids(attr(el, "DATA_FLOW", "data_flow")),
                    "priority": attr(el, "PRIORITY", "priority"),
                }
        elif stag == "ModuleVerification":
            for el in section:
                tag = local(el.tag)
                if not (tag.startswith("V-M-") or tag.startswith("V-")):
                    continue
                module = attr(el, "MODULE", "module")
                status = attr(el, "STATUS", "status")
                data.verifications[tag] = {
                    "module": module,
                    "status": status,
                    "priority": attr(el, "PRIORITY", "priority"),
                }


def load_grace_data(project_root: Path) -> tuple[GraceData, dict[str, Path]]:
    paths = find_docs(project_root)
    data = GraceData()
    kg = load_xml(paths["knowledge_graph"])
    if kg is not None:
        parse_knowledge_graph(kg, data)
    dp = load_xml(paths["development_plan"])
    if dp is not None:
        parse_development_plan(dp, data)
    req = load_xml(paths["requirements"])
    if req is not None:
        parse_requirements(req, data)
    vp = load_xml(paths["verification_plan"])
    if vp is not None:
        parse_verification(vp, data)
    return data, paths


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------


def graph_modules_deps(data: GraceData, *, limit: int | None = None) -> Graph:
    g = Graph(title="GRACE Module Dependencies")
    mods = sorted(data.modules.keys())
    if limit:
        # prefer non-stub-looking modules with edges
        connected: set[str] = set()
        for a, b in data.depends:
            connected.add(a)
            connected.add(b)
        mods = sorted(connected)[:limit] if connected else mods[:limit]
        allow = set(mods)
    else:
        allow = set(mods)

    for mid in sorted(allow):
        meta = data.modules.get(mid, {})
        label = f"{mid}\\n{meta.get('name', '')}"
        status = meta.get("status") or ""
        if status:
            label += f"\\n[{status}]"
        g.add_node(mid, label)
        mtype = meta.get("type") or "module"
        g.add_to_group(mtype or "module", mid)

    for src, dst in data.depends:
        if src in allow and dst in allow:
            g.add_edge(src, dst, "depends_on")
    return g


def graph_modules_verification(data: GraceData) -> Graph:
    g = Graph(title="GRACE Modules ↔ Verification")
    for mid, meta in sorted(data.modules.items()):
        g.add_node(mid, f"{mid}\\n{meta.get('name', '')}")
        g.add_to_group("module", mid)
        vref = meta.get("verification") or ""
        for vid in split_ids(vref):
            g.add_node(vid, vid)
            g.add_to_group("verification", vid)
            g.add_edge(mid, vid, "verified_by")
    for vid, vmeta in sorted(data.verifications.items()):
        g.add_node(vid, f"{vid}\\n[{vmeta.get('status', '')}]")
        g.add_to_group("verification", vid)
        mod = vmeta.get("module") or ""
        if mod:
            g.add_node(mod, mod)
            g.add_to_group("module", mod)
            g.add_edge(mod, vid, "verified_by")
    return g


def graph_use_cases_flows(data: GraceData) -> Graph:
    g = Graph(title="GRACE Use Cases ↔ Flows")
    for uc, meta in sorted(data.use_cases.items()):
        g.add_node(uc, f"{uc}\\n{meta.get('name', '')[:60]}")
        g.add_to_group("use_case", uc)
        for fid in meta.get("flows") or []:
            g.add_node(fid, fid)
            if fid.startswith("DF-"):
                g.add_to_group("data_flow", fid)
            elif fid.startswith("Phase-"):
                g.add_to_group("phase", fid)
            else:
                g.add_to_group("other", fid)
            g.add_edge(uc, fid, "related_flow")
    for vf, meta in sorted(data.critical_flows.items()):
        g.add_node(vf, f"{vf}\\n{meta.get('name', '')}")
        g.add_to_group("critical_flow", vf)
        for uc in meta.get("use_cases") or []:
            g.add_node(uc, uc)
            g.add_to_group("use_case", uc)
            g.add_edge(vf, uc, "uses")
        for df in meta.get("data_flow") or []:
            g.add_node(df, df)
            g.add_to_group("data_flow", df)
            g.add_edge(vf, df, "data_flow")
    for df, meta in sorted(data.data_flows.items()):
        g.add_node(df, f"{df}\\n{meta.get('name', '')}")
        g.add_to_group("data_flow", df)
    return g


def graph_phases_steps(data: GraceData) -> Graph:
    g = Graph(title="GRACE Phases and Steps")
    for pid, meta in sorted(data.phases.items(), key=lambda x: _phase_key(x[0])):
        g.add_node(pid, f"{pid}\\n{meta.get('name', '')}\\n[{meta.get('status', '')}]")
        g.add_to_group("phase", pid)
    for sid, meta in sorted(data.steps.items()):
        g.add_node(sid, f"{sid}\\n{meta.get('name', '')}\\n[{meta.get('status', '')}]")
        g.add_to_group("step", sid)
        phase = meta.get("phase")
        if phase:
            g.add_edge(phase, sid, "contains")
        vref = meta.get("verification") or ""
        if vref:
            g.add_node(vref, vref)
            g.add_to_group("verification", vref)
            g.add_edge(sid, vref, "verified_by")
    return g


def graph_cross_links(data: GraceData, *, limit: int = 80) -> Graph:
    g = Graph(title="GRACE CrossLinks (knowledge-graph)")
    edges = data.cross_links[:limit]
    for src, dst, rel in edges:
        short = (rel[:40] + "…") if len(rel) > 40 else rel
        g.add_node(src, src)
        g.add_node(dst, dst)
        g.add_to_group("module", src)
        g.add_to_group("module", dst)
        g.add_edge(src, dst, short)
    return g


def graph_overview(data: GraceData) -> Graph:
    """Compact overview: counts as nodes + sample hubs."""
    g = Graph(title="GRACE Overview")
    hubs = {
        "Modules": f"Modules\\n{len(data.modules)}",
        "Verifications": f"Verifications\\n{len(data.verifications)}",
        "UseCases": f"UseCases\\n{len(data.use_cases)}",
        "Phases": f"Phases\\n{len(data.phases)}",
        "DataFlows": f"DataFlows\\n{len(data.data_flows)}",
        "CriticalFlows": f"CriticalFlows\\n{len(data.critical_flows)}",
        "DependsEdges": f"depends_on\\n{len(data.depends)}",
        "CrossLinks": f"CrossLinks\\n{len(data.cross_links)}",
    }
    for hid, label in hubs.items():
        g.add_node(hid, label)
        g.add_to_group("hub", hid)
    g.add_edge("Modules", "DependsEdges", "has")
    g.add_edge("Modules", "Verifications", "verified_by")
    g.add_edge("Modules", "CrossLinks", "linked")
    g.add_edge("UseCases", "DataFlows", "related")
    g.add_edge("UseCases", "CriticalFlows", "covered_by")
    g.add_edge("Phases", "Modules", "implements")
    g.add_edge("CriticalFlows", "Verifications", "checks")
    return g


def _phase_key(pid: str) -> tuple:
    try:
        return (int(pid.split("-", 1)[1]),)
    except (IndexError, ValueError):
        return (9999, pid)


# ---------------------------------------------------------------------------
# Exporters: Graphviz + Mermaid
# ---------------------------------------------------------------------------


def _safe_id(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", node_id)


def to_graphviz(g: Graph) -> str:
    # Large graphs: avoid compound cluster ranking issues in Graphviz
    large = len(g.nodes) > 80 or len(g.edges) > 100
    graph_attrs = (
        f'fontname="Helvetica", fontsize=12, label={_gv_str(g.title)}, labelloc=t, '
        "overlap=false, splines=true, newrank=true"
    )
    if large:
        graph_attrs += ", concentrate=true"
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        f"  graph [{graph_attrs}];",
        '  node [shape=box, style="rounded,filled", fillcolor="#E8F1FF", fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9, color="#555555"];',
        "",
    ]
    # Skip subgraph clusters for huge graphs (init_rank failures)
    use_clusters = not large
    colors = {
        "module": "#E8F1FF",
        "verification": "#F3E8FF",
        "use_case": "#E8FFE8",
        "data_flow": "#FFF6E0",
        "critical_flow": "#FFE8E8",
        "phase": "#E0F7FA",
        "step": "#F5F5F5",
        "hub": "#FFFDE7",
        "other": "#EEEEEE",
        "ENTRY_POINT": "#C8E6C9",
        "CORE_LOGIC": "#BBDEFB",
        "UTILITY": "#E0E0E0",
        "INTEGRATION": "#FFE0B2",
        "UI_COMPONENT": "#F8BBD0",
        "DATA_LAYER": "#D1C4E9",
    }
    emitted: set[str] = set()
    if use_clusters and g.node_groups:
        for group, ids in sorted(g.node_groups.items()):
            fill = colors.get(group, colors["other"])
            lines.append(f"  subgraph cluster_{_safe_id(group)} {{")
            lines.append(f"    label={_gv_str(group)};")
            lines.append("    style=rounded;")
            lines.append(f"    bgcolor={_gv_str(fill)};")
            for nid in sorted(ids):
                if nid not in g.nodes:
                    continue
                lines.append(f"    {_safe_id(nid)} [label={_gv_str(g.nodes[nid])}];")
                emitted.add(nid)
            lines.append("  }")
            lines.append("")
    for nid, label in sorted(g.nodes.items()):
        if nid in emitted:
            continue
        fill = colors["other"]
        for group, ids in g.node_groups.items():
            if nid in ids:
                fill = colors.get(group, colors["other"])
                break
        lines.append(
            f"  {_safe_id(nid)} [label={_gv_str(label)}, fillcolor={_gv_str(fill)}];"
        )
    lines.append("")
    for src, dst, label in g.edges:
        if label:
            lines.append(f"  {_safe_id(src)} -> {_safe_id(dst)} [label={_gv_str(label)}];")
        else:
            lines.append(f"  {_safe_id(src)} -> {_safe_id(dst)};")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _gv_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_mermaid(g: Graph, *, direction: str = "LR") -> str:
    """Emit Mermaid flowchart (GitHub/Obsidian friendly)."""
    lines = [
        f"%% {g.title}",
        f"flowchart {direction}",
    ]
    # declare nodes
    for nid, label in sorted(g.nodes.items()):
        text_label = label.replace("\\n", "<br/>")
        # Mermaid node text: use quotes for special chars
        safe = text_label.replace('"', "'")
        lines.append(f'  {_safe_id(nid)}["{safe}"]')
    lines.append("")
    for src, dst, label in g.edges:
        if label:
            lab = label.replace('"', "'")
            lines.append(f"  {_safe_id(src)} -->|{lab}| {_safe_id(dst)}")
        else:
            lines.append(f"  {_safe_id(src)} --> {_safe_id(dst)}")
    lines.append("")
    return "\n".join(lines)


def to_mermaid_markdown(g: Graph, *, direction: str = "LR") -> str:
    body = to_mermaid(g, direction=direction)
    return f"# {g.title}\n\n```mermaid\n{body}```\n"


# ---------------------------------------------------------------------------
# Graphviz binary → PNG / SVG
# ---------------------------------------------------------------------------


def find_dot_binary() -> Path | None:
    """Locate Graphviz `dot` on PATH or common Windows install dirs."""
    which = shutil.which("dot")
    if which:
        return Path(which)
    candidates = [
        Path(r"C:\Program Files\Graphviz\bin\dot.exe"),
        Path(r"C:\Program Files (x86)\Graphviz\bin\dot.exe"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Graphviz" / "bin" / "dot.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Graphviz"
        / "bin"
        / "dot.exe",
        Path.home() / "scoop" / "apps" / "graphviz" / "current" / "bin" / "dot.exe",
        # Local portable bootstrap (tools/grace_graphs/.graphviz/...)
        Path(__file__).resolve().parent / ".graphviz" / "bin" / "dot.exe",
        Path(__file__).resolve().parent / ".graphviz" / "Graphviz" / "bin" / "dot.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # shallow search under tools/grace_graphs/.graphviz
    local_root = Path(__file__).resolve().parent / ".graphviz"
    if local_root.is_dir():
        for hit in local_root.rglob("dot.exe"):
            return hit
        for hit in local_root.rglob("dot"):
            if hit.is_file():
                return hit
    return None


def render_dot(
    dot_path: Path,
    *,
    out_svg: Path,
    out_png: Path,
    dot_bin: Path,
    formats: Iterable[str] = ("svg", "png"),
    engines: Iterable[str] = ("dot", "fdp", "sfdp", "neato"),
) -> list[Path]:
    """Render a .dot file to SVG and/or PNG via Graphviz (with layout engine fallbacks)."""
    written: list[Path] = []
    targets = {
        "svg": out_svg,
        "png": out_png,
    }
    # Prefer same-directory layout engines when using portable install
    bindir = dot_bin.parent
    engine_bins: list[tuple[str, Path]] = []
    for eng in engines:
        cand = bindir / (eng + (".exe" if os.name == "nt" else ""))
        if cand.is_file():
            engine_bins.append((eng, cand))
        elif eng == "dot":
            engine_bins.append((eng, dot_bin))
    if not engine_bins:
        engine_bins = [("dot", dot_bin)]

    for fmt in formats:
        fmt = fmt.lower().strip()
        if fmt not in targets:
            continue
        out_path = targets[fmt]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ok = False
        last_err = ""
        for eng_name, eng_bin in engine_bins:
            cmd = [str(eng_bin), f"-T{fmt}", str(dot_path), "-o", str(out_path)]
            if fmt == "png":
                cmd[1:1] = ["-Gdpi=120"]
            if eng_name in {"neato", "fdp", "sfdp"}:
                cmd[1:1] = ["-Goverlap=prism", "-Gsplines=true"]
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as exc:
                last_err = str(exc)
                continue
            if proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 0:
                if eng_name != "dot":
                    print(f"  rendered {dot_path.name} → {fmt} via {eng_name}")
                written.append(out_path)
                ok = True
                break
            last_err = (proc.stderr or proc.stdout or "").strip()
            # keep trying next engine; remove broken empty output
            if out_path.is_file() and out_path.stat().st_size == 0:
                out_path.unlink(missing_ok=True)
        if not ok:
            short = last_err.splitlines()[0] if last_err else "unknown error"
            print(f"WARN: render -T{fmt} failed for {dot_path.name}: {short}", file=sys.stderr)
    return written


# ---------------------------------------------------------------------------
# Registry of graphs
# ---------------------------------------------------------------------------


BUILDERS: dict[str, Callable[[GraceData], Graph]] = {
    "overview": lambda data: graph_overview(data),
    "modules-deps": lambda data: graph_modules_deps(data),
    "modules-deps-core": lambda data: graph_modules_deps(data, limit=40),
    "modules-verification": lambda data: graph_modules_verification(data),
    "use-cases-flows": lambda data: graph_use_cases_flows(data),
    "phases-steps": lambda data: graph_phases_steps(data),
    "cross-links": lambda data: graph_cross_links(data),
}


def generate_all(
    project_root: Path,
    out_dir: Path,
    *,
    only: Iterable[str] | None = None,
    render_formats: Iterable[str] = ("svg", "png"),
    skip_render: bool = False,
) -> list[Path]:
    data, paths = load_grace_data(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dot").mkdir(exist_ok=True)
    (out_dir / "mermaid").mkdir(exist_ok=True)
    (out_dir / "svg").mkdir(exist_ok=True)
    (out_dir / "png").mkdir(exist_ok=True)

    selected = list(only) if only else list(BUILDERS.keys())
    written: list[Path] = []

    render_fmts = [f.lower().strip() for f in render_formats if f.strip()]
    dot_bin = None if skip_render else find_dot_binary()
    if not skip_render and dot_bin is None:
        print(
            "WARN: Graphviz `dot` not found — wrote .dot only (no PNG/SVG).\n"
            "  Install: winget install Graphviz.Graphviz\n"
            "  Or place portable Graphviz under tools/grace_graphs/.graphviz/\n"
            "  Then re-run this script.",
            file=sys.stderr,
        )
    elif dot_bin is not None:
        print(f"Graphviz: {dot_bin}")

    index_lines = [
        "# GRACE graphs (generated)",
        "",
        "Source artifacts:",
        "",
    ]
    for role, p in paths.items():
        status = "OK" if p.is_file() else "MISSING"
        index_lines.append(f"- `{role}`: `{p.as_posix()}` — **{status}**")
    index_lines.extend(
        [
            "",
            f"Modules: **{len(data.modules)}** · depends: **{len(data.depends)}** · "
            f"V-M: **{len(data.verifications)}** · UC: **{len(data.use_cases)}** · "
            f"Phases: **{len(data.phases)}** · Steps: **{len(data.steps)}**",
            "",
            "Regenerate (DOT + PNG + SVG + Mermaid):",
            "",
            "```powershell",
            "python tools/grace_graphs/generate_grace_graphs.py --project-root .",
            "```",
            "",
            "PNG/SVG require [Graphviz](https://graphviz.org/) (`dot` on PATH).",
            "",
            "## Diagrams",
            "",
        ]
    )

    for name in selected:
        if name not in BUILDERS:
            print(f"WARN: unknown graph {name!r}, skip", file=sys.stderr)
            continue
        g = BUILDERS[name](data)
        direction = "TB" if name in {"phases-steps", "overview"} else "LR"

        dot_path = out_dir / "dot" / f"{name}.dot"
        mmd_path = out_dir / "mermaid" / f"{name}.mmd"
        md_path = out_dir / "mermaid" / f"{name}.md"
        svg_path = out_dir / "svg" / f"{name}.svg"
        png_path = out_dir / "png" / f"{name}.png"

        if direction == "TB":
            dot_text = to_graphviz(g).replace("rankdir=LR;", "rankdir=TB;")
        else:
            dot_text = to_graphviz(g)

        dot_path.write_text(dot_text, encoding="utf-8")
        mmd_path.write_text(to_mermaid(g, direction=direction), encoding="utf-8")
        md_path.write_text(to_mermaid_markdown(g, direction=direction), encoding="utf-8")
        written.extend([dot_path, mmd_path, md_path])

        if dot_bin is not None and render_fmts:
            rendered = render_dot(
                dot_path,
                out_svg=svg_path,
                out_png=png_path,
                dot_bin=dot_bin,
                formats=render_fmts,
            )
            written.extend(rendered)

        index_lines.append(f"### {name}")
        index_lines.append("")
        index_lines.append(f"- Graphviz DOT: [`dot/{name}.dot`](dot/{name}.dot)")
        if svg_path.is_file():
            index_lines.append(f"- SVG: [`svg/{name}.svg`](svg/{name}.svg)")
        if png_path.is_file():
            index_lines.append(f"- PNG: [`png/{name}.png`](png/{name}.png)")
            index_lines.append("")
            index_lines.append(f"![{g.title}](png/{name}.png)")
            index_lines.append("")
        index_lines.append(f"- Mermaid: [`mermaid/{name}.mmd`](mermaid/{name}.mmd)")
        index_lines.append(f"- Mermaid (preview): [`mermaid/{name}.md`](mermaid/{name}.md)")
        index_lines.append("")
        index_lines.append(f"**{g.title}** — nodes={len(g.nodes)} edges={len(g.edges)}")
        index_lines.append("")
        if len(g.nodes) <= 80 and len(g.edges) <= 120:
            index_lines.append("```mermaid")
            index_lines.append(to_mermaid(g, direction=direction).rstrip())
            index_lines.append("```")
            index_lines.append("")
        else:
            index_lines.append(f"_Large graph ({len(g.nodes)} nodes) — open Mermaid / SVG / PNG._")
            index_lines.append("")

    index_path = out_dir / "README.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    written.append(index_path)
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Generate Graphviz (DOT/PNG/SVG) + Mermaid graphs from docs/*.xml GRACE artifacts"
    )
    p.add_argument("--project-root", type=Path, default=Path("."), help="Repository root")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <root>/docs/grace-graphs)",
    )
    p.add_argument(
        "--only",
        type=str,
        default="",
        help=f"Comma-separated graph names. Available: {', '.join(BUILDERS)}",
    )
    p.add_argument(
        "--formats",
        type=str,
        default="svg,png",
        help="Graphviz render formats (default: svg,png). Empty string skips render.",
    )
    p.add_argument(
        "--skip-render",
        action="store_true",
        help="Write DOT + Mermaid only (no PNG/SVG)",
    )
    p.add_argument("--list", action="store_true", help="List available graphs and exit")
    args = p.parse_args(argv)

    if args.list:
        for name in BUILDERS:
            print(name)
        return 0

    root = args.project_root.resolve()
    out = (args.out or (root / "docs" / "grace-graphs")).resolve()
    only = [x.strip() for x in args.only.split(",") if x.strip()] or None
    formats = [x.strip() for x in (args.formats or "").split(",") if x.strip()]

    print(f"Project: {root}")
    print(f"Output:  {out}")
    written = generate_all(
        root,
        out,
        only=only,
        render_formats=formats,
        skip_render=args.skip_render or not formats,
    )
    print(f"Wrote {len(written)} files:")
    for path in written:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

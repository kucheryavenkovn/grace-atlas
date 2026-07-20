# FILE: tools/grace_atlas/src/grace_atlas/show_card.py
# VERSION: 0.3.1
# PURPOSE: Human / table / JSON card for `grace-atlas show`.

"""Format entity show output."""

from __future__ import annotations

import json
from typing import Any

from grace_atlas.exporters.notes import note_relpath
from grace_atlas.model import AtlasGraph, EdgeType, Node, NodeType


def build_card_data(graph: AtlasGraph, node: Node, vault_note: str) -> dict[str, Any]:
    props = node.properties or {}
    related_flows = [
        e.target
        for e in graph.edges
        if e.source == node.id and e.type == EdgeType.RELATED_FLOW
    ]
    vf_ids = [
        e.source
        for e in graph.edges
        if e.target == node.id and e.type == EdgeType.USES_USE_CASE
    ]
    modules = _ids_from_wiki_list(props.get("implements") or props.get("implemented_by") or [])
    # also depends for modules
    if node.type == NodeType.MODULE:
        modules = [node.id]
    files = _ids_from_wiki_list(props.get("implemented_in") or [])
    if node.type in {NodeType.SOURCE_FILE, NodeType.TEST_FILE}:
        files = [props.get("path") or node.name]
    verifs = _ids_from_wiki_list(props.get("verified_by") or props.get("verifies") or [])
    tests = _ids_from_wiki_list(props.get("tested_by") or [])
    if props.get("test_files"):
        tests = list(props["test_files"])
    evidence = _ids_from_wiki_list(props.get("evidence") or [])
    use_cases = _ids_from_wiki_list(props.get("belongs_to_use_case") or [])
    if node.type == NodeType.USE_CASE:
        use_cases = [node.id]

    return {
        "id": node.id,
        "name": props.get("display_name") or node.name or node.id,
        "type": node.type,
        "grace_type": props.get("grace_type") or node.type,
        "status": node.status or "",
        "description": (node.description or "")[:500],
        "use_cases": use_cases,
        "flows": related_flows,
        "verification_flows": vf_ids,
        "modules": modules if node.type != NodeType.MODULE else [node.id],
        "depends_on": _ids_from_wiki_list(props.get("depends_on") or []),
        "files": files,
        "verification": verifs,
        "tests": tests,
        "evidence": evidence,
        "gaps": list(props.get("gap_types") or []),
        "has_traceability_gap": bool(props.get("has_traceability_gap")),
        "source_state": props.get("source_state") or "declared",
        "requirement_type": props.get("requirement_type") or "",
        "obsidian_note": vault_note,
        "source_file": props.get("source_file") or "",
    }


def _ids_from_wiki_list(items: list) -> list[str]:
    out: list[str] = []
    for it in items:
        s = str(it)
        # [[Modules/M-X]] or [[Modules/M-X|label]] or bare
        if s.startswith("[[") and s.endswith("]]"):
            inner = s[2:-2]
            if "|" in inner:
                inner = inner.split("|", 1)[0]
            if "/" in inner:
                inner = inner.rsplit("/", 1)[-1]
            out.append(inner)
        else:
            out.append(s)
    return out


def format_card(data: dict[str, Any], *, fmt: str = "human") -> str:
    fmt = (fmt or "human").lower()
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if fmt == "table":
        return _table(data)
    return _human(data)


def _human(d: dict[str, Any]) -> str:
    lines = [
        f"{d['id']}  [{d['type']}]",
        f"  name:        {d['name']}",
        f"  status:      {d['status'] or '—'}",
        f"  source_state:{d['source_state']}",
    ]
    if d.get("requirement_type"):
        lines.append(f"  req_type:    {d['requirement_type']}")
    desc = d.get("description") or ""
    if desc:
        lines.append(f"  description: {desc[:200]}")
    lines.append(f"  use_cases:   {_join(d.get('use_cases'))}")
    lines.append(f"  flows:       {_join(d.get('flows'))}")
    lines.append(f"  VF:          {_join(d.get('verification_flows'))}")
    lines.append(f"  modules:     {_join(d.get('modules') if d['type'] != 'Module' else d.get('depends_on'))}")
    if d["type"] == "Module":
        lines.append(f"  depends_on:  {_join(d.get('depends_on'))}")
        lines.append(f"  self:        {d['id']}")
    lines.append(f"  files:       {_join(d.get('files'))}")
    lines.append(f"  verification:{_join(d.get('verification'))}")
    lines.append(f"  tests:       {_join(d.get('tests'))}")
    lines.append(f"  evidence:    {_join(d.get('evidence'))}")
    gaps = d.get("gaps") or []
    lines.append(f"  gaps:        {_join(gaps) if gaps else '—'}")
    lines.append(f"  note:        {d.get('obsidian_note')}")
    if d.get("source_file"):
        lines.append(f"  source:      {d['source_file']}")
    lines.append("")
    return "\n".join(lines)


def _table(d: dict[str, Any]) -> str:
    rows = [
        ("id", d["id"]),
        ("name", d["name"]),
        ("type", d["type"]),
        ("status", d["status"]),
        ("description", (d.get("description") or "")[:80]),
        ("use_cases", _join(d.get("use_cases"))),
        ("flows", _join(d.get("flows"))),
        ("modules", _join(d.get("modules"))),
        ("files", _join(d.get("files"))),
        ("verification", _join(d.get("verification"))),
        ("tests", _join(d.get("tests"))),
        ("evidence", _join(d.get("evidence"))),
        ("gaps", _join(d.get("gaps"))),
        ("obsidian_note", d.get("obsidian_note")),
    ]
    w = max(len(k) for k, _ in rows)
    lines = [f"{k.ljust(w)}  {v}" for k, v in rows]
    lines.append("")
    return "\n".join(lines)


def _join(items: list | None) -> str:
    if not items:
        return "—"
    return ", ".join(str(x) for x in items[:12]) + ("…" if len(items) > 12 else "")

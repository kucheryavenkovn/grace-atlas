# FILE: tools/grace_atlas/src/grace_atlas/patches/planner.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Plan minimal XML changes for a GracePatch without writing.
#   SCOPE: locate knowledge-graph CrossLink targets, preconditions, planned diff
#   DEPENDS: schema, config, graph, model
#   LINKS: Phase 3C
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Patch planner (read-only planning)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from grace_atlas.config import AtlasConfig
from grace_atlas.discovery import discover_artifacts
from grace_atlas.model import AtlasGraph, EdgeType
from grace_atlas.patches.schema import GracePatch, PatchOperation, validate_patch_schema


@dataclass
class PlannedFileChange:
    path: str
    action: str  # insert_crosslink | remove_crosslink | update_attr | noop
    description: str
    before_snippet: str = ""
    after_snippet: str = ""
    xpath_hint: str = ""


@dataclass
class PlanResult:
    ok: bool
    patch: GracePatch
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    changes: list[PlannedFileChange] = field(default_factory=list)
    preconditions: list[dict[str, Any]] = field(default_factory=list)
    planned_diff: str = ""
    validation_plan: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "patchId": self.patch.patch_id,
            "errors": self.errors,
            "warnings": self.warnings,
            "affectedFiles": self.affected_files,
            "changes": [
                {
                    "path": c.path,
                    "action": c.action,
                    "description": c.description,
                    "beforeSnippet": c.before_snippet,
                    "afterSnippet": c.after_snippet,
                    "xpathHint": c.xpath_hint,
                }
                for c in self.changes
            ],
            "preconditions": self.preconditions,
            "plannedDiff": self.planned_diff,
            "validationPlan": self.validation_plan,
            "summary_text": self._summary_text(),
        }

    def _summary_text(self) -> str:
        lines = [
            f"Patch {self.patch.patch_id}: {'OK to proceed to validate' if self.ok else 'BLOCKED'}",
            f"Operations: {len(self.patch.operations)}",
            f"Affected files: {len(self.affected_files)}",
        ]
        for e in self.errors:
            lines.append(f"ERROR: {e}")
        for w in self.warnings:
            lines.append(f"WARN: {w}")
        for c in self.changes:
            lines.append(f"  {c.action}: {c.path} — {c.description}")
        if self.planned_diff:
            lines.append("--- planned diff ---")
            lines.append(self.planned_diff)
        return "\n".join(lines) + "\n"


def _file_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _find_kg(config: AtlasConfig) -> Path | None:
    arts = discover_artifacts(config)
    raw = arts.knowledge_graph
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = config.repo_root / p
        if p.is_file():
            return p.resolve()
    # fallback
    for cand in [
        config.repo_root / "docs" / "knowledge-graph.xml",
        config.repo_root / "knowledge-graph.xml",
    ]:
        if cand.is_file():
            return cand.resolve()
    return None


def _edge_exists(graph: AtlasGraph, source: str, target: str, relation: str) -> bool:
    for e in graph.edges:
        if e.source == source and e.target == target and e.type == relation:
            return True
    return False


def _crosslink_xml(source: str, target: str, relation: str, reason: str) -> str:
    # Minimal CrossLink element matching common GRACE style
    desc = reason or f"{relation} {source} -> {target}"
    return (
        f'  <CrossLink from="{source}" to="{target}" relation="{relation}">'
        f"{_xml_escape(desc)}</CrossLink>\n"
    )


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def plan_patch(
    config: AtlasConfig,
    patch: GracePatch,
    graph: AtlasGraph,
    *,
    current_model_hash: str | None = None,
) -> PlanResult:
    errors = validate_patch_schema(patch)
    result = PlanResult(ok=False, patch=patch, errors=list(errors))

    if patch.project_hash and current_model_hash and patch.project_hash != current_model_hash:
        result.errors.append(
            f"stale projectHash: patch expects {patch.project_hash}, model is {current_model_hash}"
        )

    kg = _find_kg(config)
    if kg is None:
        result.errors.append("knowledge-graph.xml not found; cannot plan edge mutations")
        return result

    kg_text = kg.read_text(encoding="utf-8")
    kg_hash = _file_hash(kg)
    result.preconditions.append(
        {
            "file": str(kg.relative_to(config.repo_root)).replace("\\", "/"),
            "hash": kg_hash,
        }
    )

    diff_parts: list[str] = []
    for i, op in enumerate(patch.operations):
        if op.operation in {"add_edge", "create_verification_link"}:
            rel = op.relation or (
                EdgeType.VERIFIED_BY if op.operation == "create_verification_link" else ""
            )
            src, tgt = op.source or "", op.target or ""
            if src not in graph.nodes:
                result.errors.append(f"op[{i}]: source entity missing: {src}")
                continue
            if tgt not in graph.nodes:
                result.errors.append(f"op[{i}]: target entity missing: {tgt}")
                continue
            if _edge_exists(graph, src, tgt, rel):
                result.errors.append(f"op[{i}]: edge already exists {src}|{rel}|{tgt}")
                continue
            if op.expected_source_state == "missing" and _edge_exists(graph, src, tgt, rel):
                result.errors.append(f"op[{i}]: expected missing edge but found")
                continue
            snippet = _crosslink_xml(src, tgt, rel, op.reason)
            result.changes.append(
                PlannedFileChange(
                    path=str(kg.relative_to(config.repo_root)).replace("\\", "/"),
                    action="insert_crosslink",
                    description=f"Add {rel} {src} → {tgt}",
                    before_snippet="",
                    after_snippet=snippet.strip(),
                    xpath_hint="//CrossLinks/CrossLink",
                )
            )
            diff_parts.append(f"--- a/{kg.name}\n+++ b/{kg.name}\n+{snippet.rstrip()}")
            if str(kg) not in result.affected_files:
                result.affected_files.append(str(kg.relative_to(config.repo_root)).replace("\\", "/"))

        elif op.operation == "remove_edge":
            rel = op.relation or ""
            src, tgt = op.source or "", op.target or ""
            if not _edge_exists(graph, src, tgt, rel):
                result.errors.append(f"op[{i}]: edge not found {src}|{rel}|{tgt}")
                continue
            # Find matching CrossLink in text
            pattern = re.compile(
                rf'<CrossLink[^>]*from=["\']{re.escape(src)}["\'][^>]*to=["\']{re.escape(tgt)}["\'][^>]*/?>'
                rf'.*?(?:</CrossLink>)?',
                re.DOTALL | re.IGNORECASE,
            )
            # also relation attribute variants
            pattern2 = re.compile(
                rf'<CrossLink[^>]*(?:from=["\']{re.escape(src)}["\'][^>]*to=["\']{re.escape(tgt)}["\']|'
                rf'to=["\']{re.escape(tgt)}["\'][^>]*from=["\']{re.escape(src)}["\'])[^>]*>.*?</CrossLink>\s*',
                re.DOTALL | re.IGNORECASE,
            )
            m = pattern2.search(kg_text) or pattern.search(kg_text)
            before = m.group(0) if m else f"(edge present in graph, XML form may differ: {src}->{tgt})"
            result.changes.append(
                PlannedFileChange(
                    path=str(kg.relative_to(config.repo_root)).replace("\\", "/"),
                    action="remove_crosslink",
                    description=f"Remove {rel} {src} → {tgt}",
                    before_snippet=before.strip()[:500],
                    after_snippet="",
                    xpath_hint="//CrossLink",
                )
            )
            diff_parts.append(f"--- a/{kg.name}\n+++ b/{kg.name}\n-{before.strip()[:200]}")
            rel_path = str(kg.relative_to(config.repo_root)).replace("\\", "/")
            if rel_path not in result.affected_files:
                result.affected_files.append(rel_path)

        elif op.operation in {"update_property", "update_status", "assign_to_phase", "add_evidence_reference"}:
            # First version: plan as graph-level intent recorded for knowledge-graph notes;
            # only CrossLink-style ops rewrite XML. Property updates require element location.
            entity = op.entity_id or op.source or ""
            if entity and entity not in graph.nodes:
                result.errors.append(f"op[{i}]: entity missing: {entity}")
                continue
            result.warnings.append(
                f"op[{i}] {op.operation}: property-level XML rewrite is limited; "
                "will apply as CrossLink/meta when possible, else rejected at validate"
            )
            if op.operation == "assign_to_phase" and op.entity_id and op.target:
                # Represent as planned_in edge
                rel = EdgeType.PLANNED_IN
                if _edge_exists(graph, op.entity_id, op.target, rel):
                    result.errors.append(f"op[{i}]: already assigned to phase")
                    continue
                snippet = _crosslink_xml(op.entity_id, op.target, rel, op.reason or "assign_to_phase")
                result.changes.append(
                    PlannedFileChange(
                        path=str(kg.relative_to(config.repo_root)).replace("\\", "/"),
                        action="insert_crosslink",
                        description=f"Assign {op.entity_id} to phase {op.target}",
                        after_snippet=snippet.strip(),
                    )
                )
                rel_path = str(kg.relative_to(config.repo_root)).replace("\\", "/")
                if rel_path not in result.affected_files:
                    result.affected_files.append(rel_path)
            elif op.operation == "add_evidence_reference" and op.source and op.target:
                rel = EdgeType.PRODUCES_EVIDENCE
                snippet = _crosslink_xml(op.source, op.target, rel, op.reason or "add_evidence_reference")
                result.changes.append(
                    PlannedFileChange(
                        path=str(kg.relative_to(config.repo_root)).replace("\\", "/"),
                        action="insert_crosslink",
                        description=f"Evidence ref {op.source} → {op.target}",
                        after_snippet=snippet.strip(),
                    )
                )
                rel_path = str(kg.relative_to(config.repo_root)).replace("\\", "/")
                if rel_path not in result.affected_files:
                    result.affected_files.append(rel_path)
            else:
                result.errors.append(
                    f"op[{i}]: {op.operation} not fully supported for XML apply in this version "
                    "(use add_edge/remove_edge/assign_to_phase/add_evidence_reference/create_verification_link)"
                )

    result.planned_diff = "\n".join(diff_parts)
    result.validation_plan = [
        "copy affected XML to temp",
        "apply planned text mutations",
        "XML parse",
        "rebuild ProjectGraph",
        "compare diagnostics",
        "require confirmation before atomic write",
    ]
    result.ok = len(result.errors) == 0 and len(result.changes) > 0
    if len(result.errors) == 0 and len(result.changes) == 0:
        result.errors.append("no applicable file changes planned")
        result.ok = False
    # Verify planned XML fragments are well-formed-ish
    for c in result.changes:
        if c.after_snippet:
            try:
                ET.fromstring(c.after_snippet)
            except ET.ParseError as exc:
                result.warnings.append(f"snippet parse warning: {exc}")
    return result

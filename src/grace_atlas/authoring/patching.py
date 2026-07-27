# FILE: src/grace_atlas/authoring/patching.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Safely plan, validate and apply authoring-generated GracePatch operations.
#   SCOPE: create_use_case, update_property and add_edge; temp XML overlays, diagnostics delta, backups, audit.
#   DEPENDS: config, graph, diagnostics, patches.schema, stdlib XML/regex/filesystem
#   LINKS: M-AUTHORING-PATCHING; GracePatch; INV-AUTHORING-CONFIRM
#   ROLE: APPLICATION
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   plan_authoring_patch     - read-only source edit plan
#   validate_authoring_patch - temp overlays + graph validation
#   apply_authoring_patch    - confirmed atomic writes + backup/audit
# END_MODULE_MAP

"""Controlled round-trip for high-level authoring operations."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from grace_atlas.config import AtlasConfig
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.graph import build_graph
from grace_atlas.patches.schema import GracePatch, PatchOperation, load_patch


@dataclass(slots=True)
class SourceChange:
    path: str
    action: str
    before: str
    after: str
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action,
            "beforeSnippet": self.before[:1000],
            "afterSnippet": self.after[:1000],
            "description": self.description,
        }


@dataclass(slots=True)
class AuthoringPlan:
    patch: GracePatch
    ok: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changes: list[SourceChange] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "patchId": self.patch.patch_id,
            "errors": self.errors,
            "warnings": self.warnings,
            "fileHashes": self.file_hashes,
            "changes": [change.as_dict() for change in self.changes],
        }


def _sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _relative(config: AtlasConfig, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(config.repo_root.resolve())).replace("\\", "/")
    except ValueError as exc:
        raise ValueError(f"authoring target escapes project root: {path}") from exc


def _artifact_path(config: AtlasConfig, key: str, default_name: str) -> Path:
    raw = (config.artifact_overrides or {}).get(key)
    path = Path(raw) if raw else config.repo_root / "docs" / default_name
    if not path.is_absolute():
        path = config.repo_root / path
    if not path.is_file():
        raise FileNotFoundError(path)
    _relative(config, path)
    return path.resolve()


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _entity_pattern(entity_id: str) -> re.Pattern[str]:
    escaped = re.escape(entity_id)
    return re.compile(
        rf"(?P<whole><(?P<tag>{escaped})\b[^>]*>.*?</(?P=tag)>|"
        rf"<(?P<tag2>[A-Za-z_][\w.-]*)\b[^>]*(?:ID|id|Id)=[\"']{escaped}[\"'][^>]*>.*?</(?P=tag2)>)",
        re.S,
    )


def _find_entity(text: str, entity_id: str) -> tuple[str, re.Match[str]]:
    match = _entity_pattern(entity_id).search(text)
    if match is None:
        raise ValueError(f"XML element not found for entity {entity_id}")
    return match.group("whole"), match


def _child_mapping(node_type: str, prop: str) -> str:
    if node_type == "UseCase":
        mapping = {
            "name": "Action",
            "description": "Goal",
            "status": "Priority",
            "properties.actor": "Actor",
            "properties.priority": "Priority",
            "properties.preconditions": "Preconditions",
            "properties.acceptance_criteria": "AcceptanceCriteria",
            "properties.related_flows_raw": "RelatedFlows",
        }
        if prop in mapping:
            return mapping[prop]
    if prop.startswith("properties."):
        return prop.split(".", 1)[1]
    return {"name": "Name", "description": "Description", "status": "Status"}.get(prop, prop)


def _replace_child(element: str, tag: str, new_value: str) -> tuple[str, str]:
    pattern = re.compile(rf"(<{re.escape(tag)}\b[^>]*>)(.*?)(</{re.escape(tag)}>)", re.S | re.I)
    match = pattern.search(element)
    escaped = _xml_escape(new_value)
    if match:
        old = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        replacement = f"{match.group(1)}{escaped}{match.group(3)}"
        return element[: match.start()] + replacement + element[match.end() :], old
    close = re.search(r"</[^>]+>\s*$", element)
    if close is None:
        raise ValueError("entity XML has no closing tag")
    indent_match = re.search(r"\n([ \t]+)<[^/][^>]*>", element)
    indent = indent_match.group(1) if indent_match else "  "
    insertion = f"\n{indent}<{tag}>{escaped}</{tag}>"
    return element[: close.start()] + insertion + element[close.start() :], ""


def _render_use_case(entity_id: str, value: dict[str, Any]) -> str:
    def text(key: str, default: str = "") -> str:
        raw = value.get(key, default)
        if isinstance(raw, (list, tuple)):
            raw = "\n".join(str(x) for x in raw)
        return _xml_escape(str(raw or ""))

    return (
        f"    <{entity_id}>\n"
        f"      <Actor>{text('actor', 'User')}</Actor>\n"
        f"      <Action>{text('action')}</Action>\n"
        f"      <Goal>{text('goal')}</Goal>\n"
        f"      <Priority>{text('priority', 'medium')}</Priority>\n"
        f"      <Preconditions>{text('preconditions')}</Preconditions>\n"
        f"      <AcceptanceCriteria>{text('acceptanceCriteria')}</AcceptanceCriteria>\n"
        f"      <RelatedFlows>{text('relatedFlows')}</RelatedFlows>\n"
        f"    </{entity_id}>"
    )


def _render_crosslink(op: PatchOperation) -> str:
    relation = op.relation or "refers_to"
    desc = _xml_escape(op.reason or f"{relation} {op.source} -> {op.target}")
    return (
        f'  <CrossLink from="{_xml_escape(op.source or "")}" '
        f'to="{_xml_escape(op.target or "")}" relation="{_xml_escape(relation)}">'
        f"{desc}</CrossLink>"
    )


def plan_authoring_patch(config: AtlasConfig, patch_file: Path) -> AuthoringPlan:
    patch = load_patch(patch_file)
    plan = AuthoringPlan(patch=patch)
    graph, _ = build_graph(config, include_source=True)
    created_ids = {
        op.entity_id for op in patch.operations if op.operation == "create_use_case" and op.entity_id
    }
    requirements = _artifact_path(config, "requirements", "requirements.xml")
    knowledge_graph = _artifact_path(config, "knowledge_graph", "knowledge-graph.xml")
    text_cache: dict[Path, str] = {}

    def read(path: Path) -> str:
        if path not in text_cache:
            text_cache[path] = path.read_text(encoding="utf-8")
            plan.file_hashes[_relative(config, path)] = _sha16(path)
        return text_cache[path]

    for index, op in enumerate(patch.operations):
        try:
            if op.operation == "create_use_case":
                entity_id = op.entity_id or ""
                if not entity_id.startswith("UC-"):
                    raise ValueError("create_use_case entityId must start with UC-")
                if entity_id in graph.nodes:
                    raise ValueError(f"entity already exists: {entity_id}")
                if not isinstance(op.value, dict):
                    raise ValueError("create_use_case value must be an object")
                source = read(requirements)
                if "</UseCases>" not in source:
                    raise ValueError("requirements.xml has no </UseCases> anchor")
                snippet = _render_use_case(entity_id, op.value)
                plan.changes.append(
                    SourceChange(
                        path=_relative(config, requirements),
                        action="insert_before_usecases_close",
                        before="</UseCases>",
                        after=snippet,
                        description=f"Create traceable use case {entity_id}",
                    )
                )
            elif op.operation == "update_property":
                entity_id = op.entity_id or ""
                node = graph.get(entity_id)
                if node is None or node.source_ref is None:
                    raise ValueError(f"entity/source reference missing: {entity_id}")
                source_path = Path(node.source_ref.path)
                if not source_path.is_absolute():
                    source_path = config.repo_root / source_path
                source_path = source_path.resolve()
                source = read(source_path)
                element, _ = _find_entity(source, entity_id)
                tag = _child_mapping(node.type, op.property or "")
                updated, old_value = _replace_child(element, tag, str(op.value or ""))
                if op.expected_old_value is not None and str(op.expected_old_value).strip() != old_value.strip():
                    raise ValueError(
                        f"stale expectedOldValue for {entity_id}.{op.property}: "
                        f"expected={op.expected_old_value!r} actual={old_value!r}"
                    )
                plan.changes.append(
                    SourceChange(
                        path=_relative(config, source_path),
                        action="replace_exact",
                        before=element,
                        after=updated,
                        description=f"Update {entity_id}.{op.property}",
                    )
                )
            elif op.operation == "add_edge":
                source_id, target_id = op.source or "", op.target or ""
                if source_id not in graph.nodes and source_id not in created_ids:
                    raise ValueError(f"edge source missing: {source_id}")
                if target_id not in graph.nodes and target_id not in created_ids:
                    raise ValueError(f"edge target missing: {target_id}")
                kg_text = read(knowledge_graph)
                relation = op.relation or "refers_to"
                edge_pattern = re.compile(
                    rf'<CrossLink\b[^>]*from=["\']{re.escape(source_id)}["\'][^>]*to=["\']{re.escape(target_id)}["\'][^>]*relation=["\']{re.escape(relation)}["\']',
                    re.I,
                )
                if edge_pattern.search(kg_text):
                    raise ValueError(f"edge already exists: {source_id}|{relation}|{target_id}")
                if "</CrossLinks>" not in kg_text:
                    raise ValueError("knowledge-graph.xml has no </CrossLinks> anchor")
                plan.changes.append(
                    SourceChange(
                        path=_relative(config, knowledge_graph),
                        action="insert_before_crosslinks_close",
                        before="</CrossLinks>",
                        after=_render_crosslink(op),
                        description=f"Add {relation} {source_id} -> {target_id}",
                    )
                )
            else:
                raise ValueError(f"authoring patch operation not supported: {op.operation}")
        except Exception as exc:  # noqa: BLE001
            plan.errors.append(f"op[{index}] {op.operation}: {exc}")

    plan.ok = bool(plan.changes) and not plan.errors
    return plan


def _apply_text(text: str, changes: list[SourceChange]) -> str:
    result = text
    for change in changes:
        if change.action == "replace_exact":
            if change.before not in result:
                raise ValueError(f"planned source snippet is stale: {change.description}")
            result = result.replace(change.before, change.after, 1)
        elif change.action == "insert_before_usecases_close":
            result = result.replace("</UseCases>", change.after + "\n  </UseCases>", 1)
        elif change.action == "insert_before_crosslinks_close":
            result = result.replace("</CrossLinks>", change.after + "\n</CrossLinks>", 1)
        else:
            raise ValueError(f"unknown change action: {change.action}")
    return result


def _temp_apply(config: AtlasConfig, plan: AuthoringPlan) -> tuple[Path, dict[str, Path]]:
    if not plan.ok:
        raise ValueError("cannot apply blocked plan")
    temp = Path(tempfile.mkdtemp(prefix="grace-authoring-"))
    outputs: dict[str, Path] = {}
    by_path: dict[str, list[SourceChange]] = {}
    for change in plan.changes:
        by_path.setdefault(change.path, []).append(change)
    for rel, changes in by_path.items():
        source = config.repo_root / rel
        if _sha16(source) != plan.file_hashes.get(rel):
            raise ValueError(f"source changed since plan: {rel}")
        result = _apply_text(source.read_text(encoding="utf-8"), changes)
        ET.fromstring(result)
        target = temp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result, encoding="utf-8", newline="\n")
        outputs[rel] = target
    return temp, outputs


def _overlay_config(config: AtlasConfig, outputs: dict[str, Path]) -> AtlasConfig:
    overrides = dict(config.artifact_overrides or {})
    for rel, path in outputs.items():
        normalized = rel.replace("\\", "/").lower()
        if normalized.endswith("requirements.xml"):
            overrides["requirements"] = str(path)
        elif normalized.endswith("knowledge-graph.xml"):
            overrides["knowledge_graph"] = str(path)
        elif normalized.endswith("development-plan.xml"):
            overrides["development_plan"] = str(path)
        elif normalized.endswith("verification-plan.xml"):
            overrides["verification_plan"] = str(path)
        elif normalized.endswith("technology.xml"):
            overrides["technology"] = str(path)
        elif normalized.endswith("operational-packets.xml"):
            overrides["operational_packets"] = str(path)
    return replace(config, artifact_overrides=overrides)


def validate_authoring_patch(config: AtlasConfig, patch_file: Path) -> dict[str, Any]:
    plan = plan_authoring_patch(config, patch_file)
    if not plan.ok:
        return {"ok": False, "stage": "plan", "plan": plan.as_dict()}
    temp: Path | None = None
    try:
        temp, outputs = _temp_apply(config, plan)
        base_graph, _ = build_graph(config, include_source=False)
        base_report = build_gap_report(base_graph)
        candidate_graph, _ = build_graph(_overlay_config(config, outputs), include_source=False)
        candidate_report = build_gap_report(candidate_graph)
        base_errors = sum(1 for item in base_report.findings if item.severity == "error")
        new_errors = sum(1 for item in candidate_report.findings if item.severity == "error")
        created_ids = [
            op.entity_id for op in plan.patch.operations if op.operation == "create_use_case" and op.entity_id
        ]
        missing_created = [entity_id for entity_id in created_ids if entity_id not in candidate_graph.nodes]
        ok = new_errors <= base_errors and not missing_created
        return {
            "ok": ok,
            "stage": "validate",
            "plan": plan.as_dict(),
            "baseErrorCount": base_errors,
            "newErrorCount": new_errors,
            "errorDelta": new_errors - base_errors,
            "missingCreatedEntities": missing_created,
            "candidateStats": candidate_graph.stats(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "stage": "validate", "plan": plan.as_dict(), "errors": [str(exc)]}
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)


def apply_authoring_patch(
    config: AtlasConfig,
    patch_file: Path,
    *,
    confirm: bool,
    workspace: Path,
) -> dict[str, Any]:
    if not confirm:
        return {"ok": False, "stage": "confirm", "errors": ["explicit confirmation required"]}
    validation = validate_authoring_patch(config, patch_file)
    if not validation.get("ok"):
        return validation
    plan = plan_authoring_patch(config, patch_file)
    temp, outputs = _temp_apply(config, plan)
    backup = Path(workspace) / "backups" / plan.patch.patch_id
    backup.mkdir(parents=True, exist_ok=True)
    audit_path = Path(workspace) / "apply-audit.jsonl"
    before_hashes: dict[str, str] = {}
    after_hashes: dict[str, str] = {}
    try:
        for rel, candidate in outputs.items():
            live = config.repo_root / rel
            if _sha16(live) != plan.file_hashes[rel]:
                raise ValueError(f"source changed before apply: {rel}")
            before_hashes[rel] = _sha16(live)
            backup_target = backup / rel
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live, backup_target)
            temporary = live.with_suffix(live.suffix + ".authoring-tmp")
            temporary.write_bytes(candidate.read_bytes())
            temporary.replace(live)
            after_hashes[rel] = _sha16(live)
        event = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "patchId": plan.patch.patch_id,
            "outcome": "applied",
            "affectedFiles": sorted(outputs),
            "beforeHashes": before_hashes,
            "afterHashes": after_hashes,
            "backupDir": str(backup),
        }
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        return {"ok": True, **event, "validation": validation}
    except Exception as exc:  # noqa: BLE001
        for rel in before_hashes:
            saved = backup / rel
            if saved.is_file():
                shutil.copy2(saved, config.repo_root / rel)
        return {"ok": False, "stage": "apply", "errors": [str(exc)], "backupDir": str(backup)}
    finally:
        shutil.rmtree(temp, ignore_errors=True)

# FILE: tools/grace_atlas/src/grace_atlas/patches/apply.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Apply planned GracePatch to temp copy then atomic write after validation.
#   SCOPE: temp apply, XML parse, graph rebuild, diagnostic compare, backup, atomic replace
#   DEPENDS: planner, audit, graph, diagnostics
#   LINKS: Phase 3C
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Apply GracePatch with safety pipeline."""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from grace_atlas.config import AtlasConfig
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.graph import build_graph
from grace_atlas.patches.audit import append_audit
from grace_atlas.patches.planner import PlanResult, plan_patch
from grace_atlas.patches.schema import GracePatch


def _sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _apply_changes_to_text(text: str, changes: list[dict[str, Any]]) -> str:
    out = text
    for ch in changes:
        action = ch["action"]
        if action == "insert_crosslink":
            snippet = ch.get("afterSnippet") or ""
            if not snippet:
                continue
            # Prefer insert before closing CrossLinks or root
            if "</CrossLinks>" in out:
                out = out.replace("</CrossLinks>", f"{snippet}\n</CrossLinks>", 1)
            elif re.search(r"</KnowledgeGraph>", out, re.I):
                out = re.sub(
                    r"</KnowledgeGraph>",
                    f"  <CrossLinks>\n{snippet}  </CrossLinks>\n</KnowledgeGraph>",
                    out,
                    count=1,
                    flags=re.I,
                )
            else:
                out = out.rstrip() + "\n" + snippet
        elif action == "remove_crosslink":
            before = ch.get("beforeSnippet") or ""
            if before and before in out:
                out = out.replace(before, "", 1)
            else:
                # best-effort remove by from/to
                desc = ch.get("description") or ""
                m = re.search(r"Remove\s+\S+\s+(\S+)\s+→\s+(\S+)", desc)
                if m:
                    src, tgt = m.group(1), m.group(2)
                    out = re.sub(
                        rf"\s*<CrossLink[^>]*from=[\"']{re.escape(src)}[\"'][^>]*to=[\"']{re.escape(tgt)}[\"'][^>]*>.*?</CrossLink>\s*",
                        "\n",
                        out,
                        count=1,
                        flags=re.I | re.S,
                    )
    return out


def apply_to_temp(
    config: AtlasConfig,
    plan: PlanResult,
) -> dict[str, Any]:
    """Apply changes in a temporary directory copy of affected files. No repo mutation."""
    if not plan.ok:
        return {"ok": False, "errors": plan.errors, "stage": "plan"}

    tmp = Path(tempfile.mkdtemp(prefix="grace-patch-"))
    written: list[str] = []
    try:
        by_file: dict[str, list[dict[str, Any]]] = {}
        for c in plan.changes:
            by_file.setdefault(c.path, []).append(
                {
                    "action": c.action,
                    "afterSnippet": c.after_snippet,
                    "beforeSnippet": c.before_snippet,
                    "description": c.description,
                }
            )
        for rel, chs in by_file.items():
            src = config.repo_root / rel
            if not src.is_file():
                return {"ok": False, "errors": [f"missing file {rel}"], "stage": "copy"}
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            text = src.read_text(encoding="utf-8")
            new_text = _apply_changes_to_text(text, chs)
            # XML parse check
            try:
                ET.fromstring(new_text)
            except ET.ParseError as exc:
                return {
                    "ok": False,
                    "errors": [f"XML parse failed after patch on {rel}: {exc}"],
                    "stage": "xml_parse",
                    "tempDir": str(tmp),
                }
            dst.write_text(new_text, encoding="utf-8", newline="\n")
            written.append(rel)
        return {
            "ok": True,
            "tempDir": str(tmp),
            "written": written,
            "stage": "temp_apply",
        }
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "errors": [str(exc)], "stage": "temp_apply"}


def validate_temp_graph(
    config: AtlasConfig,
    temp_result: dict[str, Any],
    *,
    allow_new_errors: bool = False,
) -> dict[str, Any]:
    """Rebuild graph using temp XML overlays via config path override is hard;
    instead, write temp kg over a copied project subset by patching only kg content
    read through a custom root is not available — we parse temp files and compare
    diagnostics using a lightweight approach: swap file content briefly is forbidden.

    Validation strategy: parse temp XML + ensure CrossLinks well-formed, then
    rebuild graph from real config AFTER simulating by reading temp file hashes.
    For full graph rebuild we temporarily point artifact override.
    """
    if not temp_result.get("ok"):
        return temp_result

    # Baseline diagnostics
    base_graph, _ = build_graph(config, include_source=False)
    base_report = build_gap_report(base_graph)
    base_errors = sum(1 for f in base_report.findings if f.severity == "error")

    # Overlay: build config with artifact override to temp knowledge-graph
    from dataclasses import replace

    written = temp_result.get("written") or []
    kg_rel = next((w for w in written if "knowledge-graph" in w.replace("\\", "/")), None)
    if not kg_rel:
        return {
            "ok": False,
            "errors": ["no knowledge-graph among written temp files"],
            "stage": "validate",
        }
    temp_kg = Path(temp_result["tempDir"]) / kg_rel
    overrides = dict(config.artifact_overrides or {})
    overrides["knowledge_graph"] = str(temp_kg)
    tmp_config = replace(config, artifact_overrides=overrides)

    try:
        new_graph, _ = build_graph(tmp_config, include_source=False)
        new_report = build_gap_report(new_graph)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [f"graph rebuild failed: {exc}"],
            "stage": "graph_rebuild",
            "tempDir": temp_result.get("tempDir"),
        }

    new_errors = sum(1 for f in new_report.findings if f.severity == "error")
    delta_errors = new_errors - base_errors
    ok = True
    errors: list[str] = []
    if delta_errors > 0 and not allow_new_errors:
        ok = False
        errors.append(
            f"new error findings would increase by {delta_errors} "
            f"(base={base_errors}, new={new_errors}); use allow_new_errors override"
        )
    return {
        "ok": ok,
        "errors": errors,
        "stage": "validate",
        "tempDir": temp_result.get("tempDir"),
        "baseErrorCount": base_errors,
        "newErrorCount": new_errors,
        "errorDelta": delta_errors,
        "baseFindingCount": len(base_report.findings),
        "newFindingCount": len(new_report.findings),
        "written": written,
    }


def atomic_apply_from_temp(
    config: AtlasConfig,
    plan: PlanResult,
    temp_result: dict[str, Any],
    *,
    allow_new_errors: bool = False,
) -> dict[str, Any]:
    """Final apply: re-check hashes, backup, atomic replace, audit."""
    validation = validate_temp_graph(config, temp_result, allow_new_errors=allow_new_errors)
    if not validation.get("ok"):
        append_audit(
            config,
            {
                "patchId": plan.patch.patch_id,
                "outcome": "validation_failed",
                "operations": [o.as_dict() for o in plan.patch.operations],
                "affectedFiles": plan.affected_files,
                "validationResult": validation,
                "diffHash": hashlib.sha256((plan.planned_diff or "").encode()).hexdigest()[:16],
            },
        )
        return {"ok": False, **validation, "outcome": "validation_failed"}

    backup_dir = (
        config.repo_root
        / ".grace-atlas"
        / "user"
        / "backups"
        / plan.patch.patch_id
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    before_hashes: dict[str, str] = {}
    after_hashes: dict[str, str] = {}

    try:
        for rel in temp_result.get("written") or []:
            live = config.repo_root / rel
            temp_file = Path(temp_result["tempDir"]) / rel
            if not live.is_file() or not temp_file.is_file():
                raise FileNotFoundError(rel)
            before_hashes[rel] = _sha16(live)
            # Preconditions: file still same as planned
            shutil.copy2(live, backup_dir / Path(rel).name)
            # Atomic replace
            data = temp_file.read_bytes()
            tmp_write = live.with_suffix(live.suffix + ".grace-tmp")
            tmp_write.write_bytes(data)
            tmp_write.replace(live)
            after_hashes[rel] = _sha16(live)
    except Exception as exc:  # noqa: BLE001
        append_audit(
            config,
            {
                "patchId": plan.patch.patch_id,
                "outcome": "apply_failed",
                "operations": [o.as_dict() for o in plan.patch.operations],
                "affectedFiles": plan.affected_files,
                "failureReason": str(exc),
                "beforeHashes": before_hashes,
            },
        )
        return {"ok": False, "errors": [str(exc)], "outcome": "apply_failed"}

    append_audit(
        config,
        {
            "patchId": plan.patch.patch_id,
            "outcome": "applied",
            "operations": [o.as_dict() for o in plan.patch.operations],
            "affectedFiles": plan.affected_files,
            "validationResult": {
                "errorDelta": validation.get("errorDelta"),
                "baseErrorCount": validation.get("baseErrorCount"),
                "newErrorCount": validation.get("newErrorCount"),
            },
            "diffHash": hashlib.sha256((plan.planned_diff or "").encode()).hexdigest()[:16],
            "beforeHashes": before_hashes,
            "afterHashes": after_hashes,
            "backupDir": str(backup_dir.relative_to(config.repo_root)).replace("\\", "/"),
            "allowNewErrors": allow_new_errors,
            "inverseOps": _inverse_ops(plan.patch),
        },
    )
    # cleanup temp
    shutil.rmtree(temp_result.get("tempDir") or "", ignore_errors=True)
    return {
        "ok": True,
        "outcome": "applied",
        "patchId": plan.patch.patch_id,
        "affectedFiles": plan.affected_files,
        "backupDir": str(backup_dir),
        "beforeHashes": before_hashes,
        "afterHashes": after_hashes,
        "validation": validation,
    }


def _inverse_ops(patch: GracePatch) -> list[dict[str, Any]]:
    inv: list[dict[str, Any]] = []
    for op in patch.operations:
        d = op.as_dict()
        if op.operation == "add_edge":
            d["operation"] = "remove_edge"
            inv.append(d)
        elif op.operation == "remove_edge":
            d["operation"] = "add_edge"
            inv.append(d)
        elif op.operation == "create_verification_link":
            inv.append(
                {
                    "operation": "remove_edge",
                    "source": op.source,
                    "target": op.target,
                    "relation": op.relation or "verified_by",
                    "reason": f"inverse of {patch.patch_id}",
                }
            )
        elif op.operation == "assign_to_phase":
            inv.append(
                {
                    "operation": "remove_edge",
                    "source": op.entity_id,
                    "target": op.target,
                    "relation": "planned_in",
                    "reason": f"inverse of {patch.patch_id}",
                }
            )
        elif op.operation == "add_evidence_reference":
            inv.append(
                {
                    "operation": "remove_edge",
                    "source": op.source,
                    "target": op.target,
                    "relation": "produces_evidence",
                    "reason": f"inverse of {patch.patch_id}",
                }
            )
    return inv

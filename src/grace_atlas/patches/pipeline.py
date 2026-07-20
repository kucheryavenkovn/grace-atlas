# FILE: tools/grace_atlas/src/grace_atlas/patches/pipeline.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: High-level patch CLI pipeline: plan / validate / apply / reverse.
#   SCOPE: file I/O wrappers around planner+apply+audit
#   DEPENDS: planner, apply, audit, schema, graph, snapshots
#   LINKS: Phase 3C
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""CLI-facing patch pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.diagnostics import build_gap_report
from grace_atlas.enrichment import enrich_graph
from grace_atlas.graph import build_graph
from grace_atlas.patches.apply import apply_to_temp, atomic_apply_from_temp, validate_temp_graph
from grace_atlas.patches.audit import find_audit_entry
from grace_atlas.patches.planner import plan_patch
from grace_atlas.patches.schema import GracePatch, load_patch, new_patch
from grace_atlas.snapshots import build_and_write_snapshot, model_dir_for
from grace_atlas.snapshots.builder import load_snapshot
from grace_atlas.snapshots.validator import SnapshotValidationError


def _current_hash(config: AtlasConfig) -> str | None:
    try:
        data = load_snapshot(model_dir_for(config))
        return data["manifest"].get("modelHash")
    except (SnapshotValidationError, OSError, KeyError):
        return None


def _graph(config: AtlasConfig):
    graph, _ = build_graph(config, include_source=True)
    report = build_gap_report(graph)
    enrich_graph(graph, report)
    return graph, report


def plan_patch_file(config: AtlasConfig, patch_file: Path) -> dict[str, Any]:
    patch = load_patch(patch_file)
    graph, _ = _graph(config)
    plan = plan_patch(config, patch, graph, current_model_hash=_current_hash(config))
    return plan.as_dict()


def validate_patch_file(config: AtlasConfig, patch_file: Path) -> dict[str, Any]:
    patch = load_patch(patch_file)
    graph, _ = _graph(config)
    plan = plan_patch(config, patch, graph, current_model_hash=_current_hash(config))
    if not plan.ok:
        return {"ok": False, "stage": "plan", **plan.as_dict()}
    temp = apply_to_temp(config, plan)
    if not temp.get("ok"):
        return temp
    validation = validate_temp_graph(config, temp, allow_new_errors=False)
    # cleanup temp on validate-only
    if temp.get("tempDir"):
        shutil.rmtree(temp["tempDir"], ignore_errors=True)
    return {
        "ok": bool(validation.get("ok")),
        "stage": "validate",
        "plan": plan.as_dict(),
        "validation": validation,
    }


def apply_patch_file(
    config: AtlasConfig,
    patch_file: Path,
    *,
    allow_new_errors: bool = False,
) -> dict[str, Any]:
    patch = load_patch(patch_file)
    graph, report = _graph(config)
    plan = plan_patch(config, patch, graph, current_model_hash=_current_hash(config))
    if not plan.ok:
        return {"ok": False, "stage": "plan", **plan.as_dict()}
    temp = apply_to_temp(config, plan)
    if not temp.get("ok"):
        return temp
    result = atomic_apply_from_temp(
        config, plan, temp, allow_new_errors=allow_new_errors
    )
    if result.get("ok"):
        # rebuild snapshot after mutation
        graph2, report2 = _graph(config)
        snap = build_and_write_snapshot(graph2, report2, config)
        result["snapshot"] = {
            "modelHash": snap["modelHash"],
            "model_dir": snap["model_dir"],
        }
    return result


def reverse_patch(config: AtlasConfig, patch_id: str) -> dict[str, Any]:
    entry = find_audit_entry(config, patch_id)
    if not entry:
        return {"ok": False, "errors": [f"audit entry not found for {patch_id}"]}
    if entry.get("outcome") != "applied":
        return {"ok": False, "errors": [f"patch outcome is {entry.get('outcome')}, not applied"]}
    inv = entry.get("inverseOps") or []
    if not inv:
        return {"ok": False, "errors": ["no inverseOps stored for this patch"]}
    reverse = new_patch(
        inv,
        project_hash=_current_hash(config),
        author={"type": "human", "name": "reverse-patch"},
    )
    reverse.meta["reverses"] = patch_id
    return {
        "ok": True,
        "reversePatch": reverse.as_dict(),
        "note": "Write reversePatch to a file and run: grace-atlas patch apply --confirm <file>",
    }

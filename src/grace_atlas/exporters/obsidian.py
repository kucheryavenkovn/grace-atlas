# FILE: tools/grace_atlas/src/grace_atlas/exporters/obsidian.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Safely export AtlasGraph to Obsidian vault with atomic replace and markers.
#   SCOPE: notes, indexes, diagnostics, canvases, safety checks; no arbitrary rmtree
#   DEPENDS: markdown, canvas, diagnostics, notes
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Safe Obsidian vault export."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.diagnostics import GapReport, build_gap_report, render_diagnostics_pages
from grace_atlas.exporters.canvas import build_all_canvases, validate_canvas_file_refs
from grace_atlas.exporters.markdown import (
    GENERATED_BANNER,
    render_home,
    render_index,
    render_node_note,
    utc_now_iso,
)
from grace_atlas.exporters.notes import TYPE_FOLDERS, note_relpath
from grace_atlas.graph import graph_to_jsonable
from grace_atlas.model import AtlasGraph

logger = logging.getLogger("grace_atlas")

MARKER_NAME = ".grace-atlas-generated"
LEGACY_MARKERS = (".grace-atlas-export",)


class VaultSafetyError(RuntimeError):
    """Raised when vault path is unsafe to clean/write."""


def is_atlas_vault(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / MARKER_NAME).is_file():
        return True
    for name in LEGACY_MARKERS:
        if (path / name).is_file():
            return True
    # Empty dir is acceptable as new vault
    try:
        return not any(path.iterdir())
    except OSError:
        return False


def assert_safe_vault_path(vault: Path, repo_root: Path) -> None:
    vault = vault.resolve()
    repo_root = repo_root.resolve()
    home = Path.home().resolve()

    if vault == repo_root:
        raise VaultSafetyError(f"Vault path must not be the project root: {vault}")
    if vault == home:
        raise VaultSafetyError(f"Vault path must not be the home directory: {vault}")
    if vault == Path(vault.anchor).resolve():
        raise VaultSafetyError(f"Vault path must not be a filesystem root: {vault}")
    # Disallow obvious dangerous targets
    dangerous_names = {"windows", "system32", "program files", "users", "etc", "usr", "var"}
    if vault.name.lower() in dangerous_names and vault.parent == vault.anchor:
        raise VaultSafetyError(f"Vault path looks too general: {vault}")

    # Must be under repo or explicitly outside but never parent of repo
    try:
        vault.relative_to(repo_root)
        under_repo = True
    except ValueError:
        under_repo = False
    if not under_repo:
        # Allow absolute output outside repo, but not parent of repo
        try:
            repo_root.relative_to(vault)
            raise VaultSafetyError(f"Vault path must not be a parent of the repository: {vault}")
        except ValueError:
            pass


def _write_marker(vault: Path, config: AtlasConfig, generated_at: str) -> None:
    payload = {
        "tool": "grace-atlas",
        "version": "0.2.0",
        "project": config.project_name,
        "generated_at": generated_at,
        "marker": MARKER_NAME,
    }
    (vault / MARKER_NAME).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _populate_vault(
    vault: Path,
    graph: AtlasGraph,
    config: AtlasConfig,
    report: GapReport,
    *,
    generated_at: str,
) -> dict[str, Any]:
    written = 0
    note_paths: set[str] = set()
    by_type: dict[str, list] = {}

    for node in sorted(graph.nodes.values(), key=lambda n: (n.type, n.id)):
        rel = note_relpath(node)
        note_paths.add(rel.replace("\\", "/"))
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_node_note(node, graph, config), encoding="utf-8")
        written += 1
        by_type.setdefault(node.type, []).append(node)

    for ntype, nodes in sorted(by_type.items(), key=lambda kv: kv[0]):
        folder = TYPE_FOLDERS.get(ntype, "Other")
        idx = vault / folder / "_index.md"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(render_index(f"{ntype} index", nodes), encoding="utf-8")
        written += 1

    home = render_home(graph, config, generated_at=generated_at, gap_summary=report.summary)
    (vault / config.home_note).write_text(home, encoding="utf-8")
    written += 1

    for rel, content in render_diagnostics_pages(report, graph).items():
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written += 1

    canvas_files = build_all_canvases(graph, report)
    missing_canvas_refs: list[str] = []
    canvas_dir = vault / "Canvas"
    canvas_dir.mkdir(parents=True, exist_ok=True)
    # Remove empty/accidental .md stubs that steal wiki-links from .canvas
    # (Obsidian creates empty Project-Overview.md when link omits .canvas).
    for stale in canvas_dir.glob("*.md"):
        if stale.name != "_index.md":
            try:
                stale.unlink()
            except OSError:
                logger.warning("Could not remove stale canvas note %s", stale)

    for rel, content in canvas_files.items():
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written += 1
        data = json.loads(content)
        missing_canvas_refs.extend(validate_canvas_file_refs(data, note_paths))

    canvas_index = (
        GENERATED_BANNER
        + "\n\n---\ngenerated: true\ntags: [grace-atlas, grace/index]\n---\n\n"
        + "# Canvas index\n\n"
        + "These are **JSON Canvas** boards. Open the `.canvas` target (not a Markdown note).\n\n"
        + "- [[Canvas/Project-Overview.canvas|Project Overview]]\n"
        + "- [[Canvas/Current-Phase.canvas|Current Phase]]\n"
        + "- [[Canvas/User-Journey.canvas|User Journey]]\n"
        + "- [[Canvas/Requirement-Traceability.canvas|Requirement Traceability]]\n"
        + "- [[Canvas/Verification-Gaps.canvas|Verification Gaps]]\n\n"
        + "If a canvas looks empty: File explorer → `Canvas/` → open the `.canvas` file directly.\n"
    )
    (canvas_dir / "_index.md").write_text(canvas_index, encoding="utf-8")
    written += 1

    data_dir = vault / "_atlas"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "graph.json").write_text(
        json.dumps(graph_to_jsonable(graph), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (data_dir / "gaps.json").write_text(
        json.dumps(
            {
                "summary": report.summary,
                "findings": [
                    {
                        "code": f.code,
                        "severity": f.severity,
                        "message": f.message,
                        "entity_id": f.entity_id,
                        "provenance": f.provenance,
                        "source_path": f.source_path,
                        "source_line": f.source_line,
                        "related": f.related,
                        "details": f.details,
                    }
                    for f in report.findings
                ],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    written += 2

    _write_marker(vault, config, generated_at)

    # Minimal .obsidian only if missing — do not overwrite user graph settings
    obsidian = vault / ".obsidian"
    if not obsidian.exists():
        obsidian.mkdir(parents=True, exist_ok=True)
        (obsidian / "app.json").write_text(
            json.dumps({"alwaysUpdateLinks": True}, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "notes_written": written,
        "missing_canvas_refs": sorted(set(missing_canvas_refs)),
        "note_count": len(note_paths),
    }


def export_vault(
    graph: AtlasGraph,
    config: AtlasConfig,
    *,
    clean: bool = True,
    generated_at: str | None = None,
    report: GapReport | None = None,
) -> dict[str, Any]:
    """
    Write vault under config.vault_path using temp dir + replace when cleaning.

    Only removes an existing directory if it is a GRACE Atlas vault (marker present)
    and path passes safety checks.
    """
    vault = config.resolve_vault()
    assert_safe_vault_path(vault, config.repo_root)
    generated_at = generated_at or utc_now_iso()
    report = report or build_gap_report(graph)

    logger.info("Exporting vault to %s", vault)

    parent = vault.parent
    parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="grace-atlas-", dir=str(parent)) as tmp:
        tmp_vault = Path(tmp) / "vault"
        tmp_vault.mkdir()
        meta = _populate_vault(tmp_vault, graph, config, report, generated_at=generated_at)

        if vault.exists():
            if not is_atlas_vault(vault):
                raise VaultSafetyError(
                    f"Refusing to overwrite non-Atlas directory: {vault}. "
                    f"Add {MARKER_NAME} only by running Atlas on an empty folder, "
                    "or choose another --output path."
                )
            if clean:
                shutil.rmtree(vault)
            else:
                # Merge mode: copy files over existing
                for root, _dirs, files in os.walk(tmp_vault):
                    rel_root = Path(root).relative_to(tmp_vault)
                    dest_root = vault / rel_root
                    dest_root.mkdir(parents=True, exist_ok=True)
                    for name in files:
                        shutil.copy2(Path(root) / name, dest_root / name)
                return {
                    "vault": str(vault),
                    "nodes": len(graph.nodes),
                    "edges": len(graph.edges),
                    "gaps": report.summary,
                    "generated_at": generated_at,
                    **meta,
                }

        # Atomic-ish replace: move temp vault into place
        shutil.move(str(tmp_vault), str(vault))

    return {
        "vault": str(vault),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "gaps": report.summary,
        "generated_at": generated_at,
        **meta,
    }

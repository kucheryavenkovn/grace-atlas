# FILE: src/grace_atlas/authoring/workspace.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Persist immutable authoring drafts, translation sidecars and generated GracePatch files.
#   SCOPE: local append-only-ish filesystem workspace under .grace-atlas; no source artifact mutation.
#   DEPENDS: models, stdlib json/pathlib
#   LINKS: M-AUTHORING-WORKSPACE
#   ROLE: INFRASTRUCTURE
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   AuthoringWorkspace - safe local draft store
# END_MODULE_MAP

"""Filesystem workspace for authoring proposals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from grace_atlas.authoring.models import AuthoringDraft


class AuthoringWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.drafts_dir = self.root / "drafts"
        self.patches_dir = self.root / "patches"
        self.translations_dir = self.root / "translations"
        self.audit_path = self.root / "audit.jsonl"

    def ensure(self) -> None:
        for path in (self.drafts_dir, self.patches_dir, self.translations_dir):
            path.mkdir(parents=True, exist_ok=True)

    def save_draft(self, draft: AuthoringDraft) -> Path:
        self.ensure()
        path = self.drafts_dir / f"{draft.draft_id}.json"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(json.dumps(draft.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.append_audit({"event": "draft_created", "draftId": draft.draft_id, "kind": draft.kind, "path": str(path)})
        return path

    def save_patch(self, draft_id: str, patch: dict[str, Any]) -> Path:
        self.ensure()
        path = self.patches_dir / f"{draft_id}.grace-patch.json"
        path.write_text(json.dumps(patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.append_audit({"event": "patch_generated", "draftId": draft_id, "path": str(path)})
        return path

    def save_translation(self, language: str, entity_id: str, data: dict[str, Any]) -> Path:
        target = self.translations_dir / language
        target.mkdir(parents=True, exist_ok=True)
        safe = entity_id.replace("/", "_").replace("\\", "_")
        path = target / f"{safe}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def append_audit(self, event: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

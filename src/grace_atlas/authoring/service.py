# FILE: src/grace_atlas/authoring/service.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Application facade for standalone authoring workflows.
#   SCOPE: build graph/context, invoke optional LLM, persist drafts/patches/translations.
#   DEPENDS: graph, snapshots, authoring application modules and workspace
#   LINKS: M-AUTHORING-SERVICE
#   ROLE: APPLICATION
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   AuthoringService - context/translate/requirement facade
# END_MODULE_MAP

"""Application facade consumed by CLI, HTTP API and future GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from grace_atlas.authoring.context import build_entity_context
from grace_atlas.authoring.llm import LlmClient, build_llm_client
from grace_atlas.authoring.models import RequirementInput, TranslationInput
from grace_atlas.authoring.requirements import build_requirement_draft
from grace_atlas.authoring.settings import AuthoringSettings, load_authoring_settings
from grace_atlas.authoring.translation import build_translation_draft
from grace_atlas.authoring.workspace import AuthoringWorkspace
from grace_atlas.graph import build_graph


class AuthoringService:
    def __init__(self, atlas_config: Any, *, llm: LlmClient | None = None) -> None:
        self.config = atlas_config
        self.settings: AuthoringSettings = load_authoring_settings(atlas_config)
        self.workspace = AuthoringWorkspace(self.settings.workspace)
        self._llm = llm

    def _graph(self):
        graph, _ = build_graph(self.config, include_source=True)
        return graph

    def _project_hash(self) -> str | None:
        try:
            from grace_atlas.snapshots import model_dir_for
            from grace_atlas.snapshots.builder import load_snapshot

            data = load_snapshot(model_dir_for(self.config))
            return str(data["manifest"].get("modelHash") or "") or None
        except (OSError, KeyError, ValueError):
            return None

    def _client(self) -> LlmClient:
        if self._llm is None:
            self._llm = build_llm_client(self.settings.llm)
        return self._llm

    def context(self, entity_ids: list[str], *, depth: int | None = None, max_nodes: int | None = None) -> dict[str, Any]:
        return build_entity_context(
            self._graph(),
            entity_ids,
            depth=self.settings.context_depth if depth is None else depth,
            max_nodes=self.settings.context_max_nodes if max_nodes is None else max_nodes,
        )

    def translate(self, request: TranslationInput, *, project_hash: str | None = None) -> dict[str, Any]:
        draft, patch = build_translation_draft(
            self._graph(), request, settings=self.settings, llm=self._client(), project_hash=project_hash or self._project_hash()
        )
        draft_path = self.workspace.save_draft(draft)
        sidecar_path = self.workspace.save_translation(
            request.target_language,
            request.entity_id,
            draft.as_dict(),
        )
        patch_path: Path | None = None
        if patch is not None:
            patch_path = self.workspace.save_patch(draft.draft_id, patch)
        return {
            "ok": True,
            "draft": draft.as_dict(),
            "draftPath": str(draft_path),
            "translationPath": str(sidecar_path),
            "patch": patch,
            "patchPath": str(patch_path) if patch_path else None,
        }

    def requirement(self, request: RequirementInput, *, project_hash: str | None = None) -> dict[str, Any]:
        llm = self._client() if request.use_llm else None
        draft, patch = build_requirement_draft(
            self._graph(), request, settings=self.settings, llm=llm, project_hash=project_hash or self._project_hash()
        )
        draft_path = self.workspace.save_draft(draft)
        patch_path = self.workspace.save_patch(draft.draft_id, patch)
        return {
            "ok": True,
            "draft": draft.as_dict(),
            "draftPath": str(draft_path),
            "patch": patch,
            "patchPath": str(patch_path),
        }

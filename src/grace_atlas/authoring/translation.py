# FILE: src/grace_atlas/authoring/translation.py
# VERSION: 0.1.1
# START_MODULE_CONTRACT
#   PURPOSE: Produce traceable translation drafts and optional source-replacement GracePatch proposals.
#   SCOPE: LLM-assisted translation of selected entity fields; default output is sidecar, not source mutation.
#   DEPENDS: authoring models/context/llm/settings, grace_atlas.patches.schema
#   LINKS: M-AUTHORING-TRANSLATION; UC-AUTHOR-TRANSLATE
#   ROLE: APPLICATION
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   build_translation_draft - entity -> translated sidecar + optional GracePatch
# END_MODULE_MAP

"""Translation use case for GRACE entities."""

from __future__ import annotations

import json
from typing import Any

from grace_atlas.authoring.context import build_entity_context, evidence_from_context
from grace_atlas.authoring.llm import LlmClient
from grace_atlas.authoring.models import AuthoringDraft, TranslationInput
from grace_atlas.authoring.settings import AuthoringSettings
from grace_atlas.model import AtlasGraph
from grace_atlas.patches.schema import new_patch


def _field_value(node: Any, field: str) -> str:
    if field == "name":
        return str(node.name or "")
    if field == "description":
        return str(node.description or "")
    if field == "status":
        return str(node.status or "")
    if field.startswith("properties."):
        return str(node.properties.get(field.split(".", 1)[1], "") or "")
    raise ValueError(f"unsupported translation field: {field}")


def build_translation_draft(
    graph: AtlasGraph,
    request: TranslationInput,
    *,
    settings: AuthoringSettings,
    llm: LlmClient,
    project_hash: str | None = None,
) -> tuple[AuthoringDraft, dict[str, Any] | None]:
    node = graph.get(request.entity_id)
    if node is None:
        raise KeyError(request.entity_id)
    fields = {field: _field_value(node, field) for field in request.fields}
    fields = {key: value for key, value in fields.items() if value}
    if not fields:
        raise ValueError("selected entity fields are empty")

    context = build_entity_context(
        graph,
        [request.entity_id],
        depth=min(settings.context_depth, 1),
        max_nodes=min(settings.context_max_nodes, 12),
    )
    preserve = ", ".join(settings.translation.preserve_terms)
    system = (
        "You translate software architecture and requirements artifacts. "
        "Return one JSON object only. Preserve identifiers, code symbols and the following terms unchanged: "
        f"{preserve}. Do not add facts not present in the input."
    )
    user = json.dumps(
        {
            "task": "translate_entity_fields",
            "entityId": request.entity_id,
            "sourceLanguage": request.source_language,
            "targetLanguage": request.target_language,
            "fields": fields,
            "requiredOutput": {"translations": {field: "translated string" for field in fields}},
        },
        ensure_ascii=False,
        indent=2,
    )
    response = llm.generate_json(system=system, user=user)
    translations = response.get("translations") or {}
    if not isinstance(translations, dict):
        raise ValueError("LLM response.translations must be an object")
    clean: dict[str, str] = {}
    for field in fields:
        value = str(translations.get(field) or "").strip()
        if not value:
            raise ValueError(f"missing translated field: {field}")
        clean[field] = value

    draft = AuthoringDraft(
        kind="translation",
        title=f"{request.entity_id} → {request.target_language}",
        project_hash=project_hash,
        provider=getattr(llm, "provider", "unknown"),
        model=getattr(llm, "model", ""),
        source_language=request.source_language,
        target_language=request.target_language,
        payload={
            "entityId": request.entity_id,
            "entityType": node.type,
            "original": fields,
            "translations": clean,
            "replaceSourceRequested": request.replace_source,
        },
        evidence=evidence_from_context(context),
        meta={"contextRoots": context["roots"], "contextNodeCount": len(context["nodes"])},
    )

    patch: dict[str, Any] | None = None
    if request.replace_source:
        if not settings.allow_source_replace:
            raise PermissionError("authoring.allow_source_replace=false")
        if len(clean) != 1:
            raise ValueError(
                "source replacement is intentionally limited to one field per patch in v0.5; "
                "use --fields name or --fields description. Multi-field translations remain available as sidecars."
            )
        field, translated = next(iter(clean.items()))
        patch = new_patch(
            [
                {
                    "operation": "update_property",
                    "entityId": request.entity_id,
                    "property": field,
                    "value": translated,
                    "expectedOldValue": fields[field],
                    "reason": (
                        f"translation {request.source_language}->{request.target_language}; "
                        f"draft={draft.draft_id}"
                    ),
                }
            ],
            project_hash=project_hash,
            author={"type": "llm-assisted", "name": getattr(llm, "model", "")},
        ).as_dict()
        patch.setdefault("meta", {})["draftId"] = draft.draft_id
        patch["meta"]["kind"] = "translation"
    return draft, patch

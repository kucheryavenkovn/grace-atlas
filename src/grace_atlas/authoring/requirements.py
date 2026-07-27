# FILE: src/grace_atlas/authoring/requirements.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Draft a traceable GRACE use case from selected Atlas evidence and compile it to GracePatch.
#   SCOPE: deterministic/LLM proposal generation; no direct source mutation.
#   DEPENDS: authoring models/context/llm/settings, grace_atlas.patches.schema
#   LINKS: M-AUTHORING-REQUIREMENTS; UC-AUTHOR-REQUIREMENT
#   ROLE: APPLICATION
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   build_requirement_draft - evidence -> draft + create_use_case/link patch
# END_MODULE_MAP

"""Requirement/use-case authoring use case."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from grace_atlas.authoring.context import build_entity_context, evidence_from_context
from grace_atlas.authoring.llm import LlmClient
from grace_atlas.authoring.models import AuthoringDraft, RequirementInput
from grace_atlas.authoring.settings import AuthoringSettings
from grace_atlas.model import AtlasGraph
from grace_atlas.patches.schema import new_patch


def _default_id() -> str:
    return "UC-AUTH-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _as_strings(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    return [str(item).strip() for item in raw if str(item).strip()]


def build_requirement_draft(
    graph: AtlasGraph,
    request: RequirementInput,
    *,
    settings: AuthoringSettings,
    llm: LlmClient | None,
    project_hash: str | None = None,
) -> tuple[AuthoringDraft, dict[str, Any]]:
    if not request.evidence_ids:
        raise ValueError("at least one evidence id is required")
    context = build_entity_context(
        graph,
        request.evidence_ids,
        depth=settings.context_depth,
        max_nodes=settings.context_max_nodes,
    )

    proposal: dict[str, Any]
    provider, model = "human", ""
    if request.use_llm:
        if llm is None:
            raise ValueError("LLM is required when use_llm=true")
        provider, model = getattr(llm, "provider", "unknown"), getattr(llm, "model", "")
        system = (
            "You are a requirements analyst. Produce a single GRACE use case grounded only in the supplied Atlas evidence. "
            "Return JSON only. Every acceptance criterion must be testable. Do not invent implementation status."
        )
        user = json.dumps(
            {
                "task": "draft_traceable_use_case",
                "requested": {
                    "id": request.requirement_id or None,
                    "title": request.title or None,
                    "actor": request.actor or None,
                    "action": request.action or None,
                    "goal": request.goal or None,
                    "priority": request.priority,
                },
                "evidenceContext": context,
                "requiredOutput": {
                    "title": "short title",
                    "actor": "actor",
                    "action": "user/system action",
                    "goal": "outcome",
                    "priority": "high|medium|low",
                    "preconditions": ["..."],
                    "acceptanceCriteria": ["Given/When/Then or testable statement"],
                    "relatedFlows": ["existing DF-/VF-/Phase- id only"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        proposal = llm.generate_json(system=system, user=user)
    else:
        proposal = {
            "title": request.title,
            "actor": request.actor,
            "action": request.action,
            "goal": request.goal,
            "priority": request.priority,
            "preconditions": list(request.preconditions),
            "acceptanceCriteria": list(request.acceptance_criteria),
            "relatedFlows": list(request.related_flows),
        }

    requirement_id = request.requirement_id or _default_id()
    if requirement_id in graph.nodes:
        raise ValueError(f"entity already exists: {requirement_id}")
    if not requirement_id.startswith("UC-"):
        raise ValueError("requirement_id must start with UC-")

    payload = {
        "requirementId": requirement_id,
        "title": str(proposal.get("title") or request.title or requirement_id).strip(),
        "actor": str(proposal.get("actor") or request.actor or "User").strip(),
        "action": str(proposal.get("action") or request.action or "").strip(),
        "goal": str(proposal.get("goal") or request.goal or "").strip(),
        "priority": str(proposal.get("priority") or request.priority or "medium").strip(),
        "preconditions": _as_strings(proposal.get("preconditions") or request.preconditions),
        "acceptanceCriteria": _as_strings(proposal.get("acceptanceCriteria") or request.acceptance_criteria),
        "relatedFlows": _as_strings(proposal.get("relatedFlows") or request.related_flows),
        "evidenceIds": list(request.evidence_ids),
    }
    if not payload["action"] or not payload["goal"]:
        raise ValueError("draft must contain action and goal")
    if not payload["acceptanceCriteria"]:
        raise ValueError("draft must contain at least one acceptance criterion")

    draft = AuthoringDraft(
        kind="requirement",
        title=payload["title"],
        payload=payload,
        evidence=evidence_from_context(context),
        project_hash=project_hash,
        provider=provider,
        model=model,
        meta={"contextRoots": list(request.evidence_ids), "contextNodeCount": len(context["nodes"])},
    )

    operations: list[dict[str, Any]] = [
        {
            "operation": "create_use_case",
            "entityId": requirement_id,
            "value": payload,
            "reason": f"authoring draft {draft.draft_id}",
        }
    ]
    for evidence_id in request.evidence_ids:
        operations.append(
            {
                "operation": "add_edge",
                "source": requirement_id,
                "target": evidence_id,
                "relation": "refers_to",
                "reason": f"evidence for authoring draft {draft.draft_id}",
            }
        )
    patch = new_patch(
        operations,
        project_hash=project_hash,
        author={"type": "llm-assisted" if request.use_llm else "human", "name": model or "authoring-workbench"},
    ).as_dict()
    patch.setdefault("meta", {})["draftId"] = draft.draft_id
    patch["meta"]["kind"] = "requirement"
    return draft, patch

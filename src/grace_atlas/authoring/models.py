# FILE: src/grace_atlas/authoring/models.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Pure authoring-domain models for drafts, evidence, translations and requirement proposals.
#   SCOPE: immutable-ish dataclasses + JSON serialization; no filesystem, network or XML mutation.
#   DEPENDS: stdlib dataclasses, datetime, uuid
#   LINKS: M-AUTHORING-DOMAIN; UC-AUTHOR-TRANSLATE; UC-AUTHOR-REQUIREMENT
#   ROLE: TYPES
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   EvidenceRef       - traceable evidence item
#   AuthoringDraft    - persisted proposal produced by human or LLM
#   TranslationInput  - translation request
#   RequirementInput  - requirement/use-case request
# END_MODULE_MAP

"""Domain models for the optional GRACE Atlas authoring workbench."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

DraftKind = Literal["translation", "requirement"]
DraftStatus = Literal["draft", "reviewed", "promoted", "rejected"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    entity_id: str
    relation: str = "refers_to"
    source_path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    excerpt: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", [])}


@dataclass(slots=True)
class AuthoringDraft:
    kind: DraftKind
    title: str
    payload: dict[str, Any]
    evidence: list[EvidenceRef] = field(default_factory=list)
    draft_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_utc_now)
    status: DraftStatus = "draft"
    project_hash: str | None = None
    provider: str = "human"
    model: str = ""
    source_language: str = ""
    target_language: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": "1.0",
            "draftId": self.draft_id,
            "kind": self.kind,
            "title": self.title,
            "createdAt": self.created_at,
            "status": self.status,
            "projectHash": self.project_hash,
            "provider": self.provider,
            "model": self.model,
            "sourceLanguage": self.source_language,
            "targetLanguage": self.target_language,
            "payload": self.payload,
            "evidence": [e.as_dict() for e in self.evidence],
            "meta": self.meta,
        }


@dataclass(frozen=True, slots=True)
class TranslationInput:
    entity_id: str
    target_language: str
    fields: tuple[str, ...] = ("name", "description")
    source_language: str = "auto"
    replace_source: bool = False


@dataclass(frozen=True, slots=True)
class RequirementInput:
    evidence_ids: tuple[str, ...]
    requirement_id: str = ""
    actor: str = ""
    action: str = ""
    goal: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    priority: str = "medium"
    related_flows: tuple[str, ...] = ()
    title: str = ""
    use_llm: bool = True

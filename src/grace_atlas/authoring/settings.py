# FILE: src/grace_atlas/authoring/settings.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Load optional authoring/LLM/translation settings from grace-atlas.toml and environment.
#   SCOPE: configuration only; API keys are referenced by environment variable name and never persisted.
#   DEPENDS: stdlib tomllib, dataclasses, pathlib, os
#   LINKS: M-AUTHORING-SETTINGS; INV-AUTHORING-SECRETS
#   ROLE: CONFIG
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   LlmSettings          - OpenAI-compatible provider settings
#   TranslationSettings  - language defaults
#   AuthoringSettings    - workspace + safety policy
#   load_authoring_settings - config entry point
#   render_settings_template - safe template without secrets
# END_MODULE_MAP

"""Optional settings for the standalone authoring workbench."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class LlmSettings:
    provider: str = "disabled"
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = ""
    api_key_env: str = "GRACE_ATLAS_API_KEY"
    timeout_seconds: float = 120.0
    temperature: float = 0.1
    max_tokens: int = 4096

    @property
    def enabled(self) -> bool:
        return self.provider not in {"", "disabled", "none"} and bool(self.model)

    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["enabled"] = self.enabled
        data["apiKeyConfigured"] = bool(self.api_key())
        return data


@dataclass(frozen=True, slots=True)
class TranslationSettings:
    default_source_language: str = "auto"
    default_target_language: str = "en"
    fields: tuple[str, ...] = ("name", "description")
    preserve_terms: tuple[str, ...] = ("GRACE", "GracePatch", "M-ID", "UC", "DDD")


@dataclass(frozen=True, slots=True)
class AuthoringSettings:
    workspace: Path
    allow_source_replace: bool = False
    require_validation: bool = True
    require_confirmation: bool = True
    context_depth: int = 2
    context_max_nodes: int = 40
    llm: LlmSettings = field(default_factory=LlmSettings)
    translation: TranslationSettings = field(default_factory=TranslationSettings)

    def public_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "allowSourceReplace": self.allow_source_replace,
            "requireValidation": self.require_validation,
            "requireConfirmation": self.require_confirmation,
            "contextDepth": self.context_depth,
            "contextMaxNodes": self.context_max_nodes,
            "llm": self.llm.public_dict(),
            "translation": asdict(self.translation),
        }


def _tuple(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    if isinstance(raw, str):
        return tuple(x.strip() for x in raw.split(",") if x.strip())
    return tuple(str(x) for x in raw)


def load_authoring_settings(config: Any) -> AuthoringSettings:
    """Load authoring settings using an existing AtlasConfig-like object."""
    data: dict[str, Any] = {}
    path = getattr(config, "config_path", None)
    if path and Path(path).is_file():
        with Path(path).open("rb") as fh:
            data = tomllib.load(fh)

    root = Path(getattr(config, "repo_root", Path.cwd())).resolve()
    authoring = data.get("authoring") or {}
    llm_raw = authoring.get("llm") or data.get("llm") or {}
    tr_raw = authoring.get("translation") or {}

    workspace = Path(str(authoring.get("workspace") or ".grace-atlas/authoring"))
    if not workspace.is_absolute():
        workspace = root / workspace

    llm = LlmSettings(
        provider=str(os.getenv("GRACE_ATLAS_LLM_PROVIDER") or llm_raw.get("provider") or "disabled"),
        base_url=str(os.getenv("GRACE_ATLAS_LLM_BASE_URL") or llm_raw.get("base_url") or "http://127.0.0.1:1234/v1").rstrip("/"),
        model=str(os.getenv("GRACE_ATLAS_LLM_MODEL") or llm_raw.get("model") or ""),
        api_key_env=str(llm_raw.get("api_key_env") or "GRACE_ATLAS_API_KEY"),
        timeout_seconds=float(llm_raw.get("timeout_seconds") or 120.0),
        temperature=float(llm_raw.get("temperature") if llm_raw.get("temperature") is not None else 0.1),
        max_tokens=int(llm_raw.get("max_tokens") or 4096),
    )
    translation = TranslationSettings(
        default_source_language=str(tr_raw.get("source_language") or "auto"),
        default_target_language=str(tr_raw.get("target_language") or "en"),
        fields=_tuple(tr_raw.get("fields"), ("name", "description")),
        preserve_terms=_tuple(tr_raw.get("preserve_terms"), ("GRACE", "GracePatch", "M-ID", "UC", "DDD")),
    )
    return AuthoringSettings(
        workspace=workspace.resolve(),
        allow_source_replace=bool(authoring.get("allow_source_replace", False)),
        require_validation=bool(authoring.get("require_validation", True)),
        require_confirmation=bool(authoring.get("require_confirmation", True)),
        context_depth=max(0, int(authoring.get("context_depth") or 2)),
        context_max_nodes=max(1, int(authoring.get("context_max_nodes") or 40)),
        llm=llm,
        translation=translation,
    )


def render_settings_template() -> str:
    return '''# Optional GRACE Atlas authoring workbench settings.\n\n[authoring]\nworkspace = ".grace-atlas/authoring"\nallow_source_replace = false\nrequire_validation = true\nrequire_confirmation = true\ncontext_depth = 2\ncontext_max_nodes = 40\n\n[authoring.llm]\nprovider = "openai-compatible"\nbase_url = "http://127.0.0.1:1234/v1"\nmodel = ""\napi_key_env = "GRACE_ATLAS_API_KEY"\ntimeout_seconds = 120\ntemperature = 0.1\nmax_tokens = 4096\n\n[authoring.translation]\nsource_language = "auto"\ntarget_language = "en"\nfields = ["name", "description"]\npreserve_terms = ["GRACE", "GracePatch", "M-ID", "UC", "DDD"]\n'''

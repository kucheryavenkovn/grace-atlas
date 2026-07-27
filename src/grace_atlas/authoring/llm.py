# FILE: src/grace_atlas/authoring/llm.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Optional OpenAI-compatible LLM adapter returning strict JSON for authoring use cases.
#   SCOPE: chat/completions HTTP only; no provider-specific SDK; secrets never logged.
#   DEPENDS: authoring.settings, stdlib urllib/json
#   LINKS: M-AUTHORING-LLM; INV-AUTHORING-SECRETS
#   ROLE: INFRASTRUCTURE
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   LlmClient                 - application-facing protocol
#   OpenAICompatibleLlmClient - HTTP adapter
#   build_llm_client          - provider factory
# END_MODULE_MAP

"""Optional LLM adapter for translation and requirement drafting."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Protocol

from grace_atlas.authoring.settings import LlmSettings


class LlmClient(Protocol):
    provider: str
    model: str

    def generate_json(self, *, system: str, user: str) -> dict[str, Any]: ...


class LlmDisabledError(RuntimeError):
    pass


class LlmResponseError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise LlmResponseError("LLM response does not contain a JSON object")
        try:
            value = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LlmResponseError(f"invalid JSON returned by LLM: {exc}") from exc
    if not isinstance(value, dict):
        raise LlmResponseError("LLM response must be a JSON object")
    return value


class OpenAICompatibleLlmClient:
    provider = "openai-compatible"

    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings
        self.model = settings.model

    def generate_json(self, *, system: str, user: str) -> dict[str, Any]:
        if not self.settings.enabled:
            raise LlmDisabledError("LLM provider is disabled or model is empty")
        url = f"{self.settings.base_url}/chat/completions"
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        key = self.settings.api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise LlmResponseError(f"LLM HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LlmResponseError(f"LLM request failed: {exc}") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmResponseError("unexpected OpenAI-compatible response shape") from exc
        return _extract_json(str(content))


def build_llm_client(settings: LlmSettings) -> LlmClient:
    if settings.provider in {"openai-compatible", "openai", "lm-studio", "ollama-openai", "vllm"}:
        return OpenAICompatibleLlmClient(settings)
    raise LlmDisabledError(f"unsupported or disabled LLM provider: {settings.provider}")

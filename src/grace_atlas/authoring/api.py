# FILE: src/grace_atlas/authoring/api.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Local JSON HTTP API for authoring outside a coding agent and for a future GUI.
#   SCOPE: loopback-oriented ThreadingHTTPServer; draft generation only; no patch apply endpoint.
#   DEPENDS: authoring.service/models, stdlib http.server
#   LINKS: M-AUTHORING-API; INV-AUTHORING-NO-REMOTE-APPLY
#   ROLE: INTERFACE
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   serve_authoring_api - start local HTTP server
# END_MODULE_MAP

"""Small dependency-free local API for the future graphical workbench."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from grace_atlas.authoring.models import RequirementInput, TranslationInput
from grace_atlas.authoring.service import AuthoringService


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")


def make_handler(service: AuthoringService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GraceAtlasAuthoring/0.1"

        def _send(self, status: int, value: Any) -> None:
            body = _json_bytes(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("request JSON must be an object")
            return value

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/health":
                    self._send(HTTPStatus.OK, {"ok": True, "service": "grace-atlas-authoring"})
                    return
                if parsed.path == "/settings":
                    self._send(HTTPStatus.OK, service.settings.public_dict())
                    return
                if parsed.path == "/context":
                    query = parse_qs(parsed.query)
                    ids = [item for raw in query.get("id", []) for item in raw.split(",") if item]
                    if not ids:
                        raise ValueError("query parameter id is required")
                    self._send(HTTPStatus.OK, service.context(ids))
                    return
                self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            try:
                data = self._body()
                if self.path == "/translate":
                    request = TranslationInput(
                        entity_id=str(data.get("entityId") or ""),
                        target_language=str(data.get("targetLanguage") or service.settings.translation.default_target_language),
                        source_language=str(data.get("sourceLanguage") or service.settings.translation.default_source_language),
                        fields=tuple(data.get("fields") or service.settings.translation.fields),
                        replace_source=bool(data.get("replaceSource", False)),
                    )
                    self._send(HTTPStatus.OK, service.translate(request))
                    return
                if self.path == "/requirements":
                    request = RequirementInput(
                        evidence_ids=tuple(str(x) for x in (data.get("evidenceIds") or [])),
                        requirement_id=str(data.get("requirementId") or ""),
                        actor=str(data.get("actor") or ""),
                        action=str(data.get("action") or ""),
                        goal=str(data.get("goal") or ""),
                        acceptance_criteria=tuple(str(x) for x in (data.get("acceptanceCriteria") or [])),
                        preconditions=tuple(str(x) for x in (data.get("preconditions") or [])),
                        priority=str(data.get("priority") or "medium"),
                        related_flows=tuple(str(x) for x in (data.get("relatedFlows") or [])),
                        title=str(data.get("title") or ""),
                        use_llm=bool(data.get("useLlm", True)),
                    )
                    self._send(HTTPStatus.OK, service.requirement(request))
                    return
                self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            except json.JSONDecodeError as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"invalid JSON: {exc}"})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[grace-atlas-authoring] {self.address_string()} {fmt % args}")

    return Handler


def serve_authoring_api(service: AuthoringService, *, bind: str = "127.0.0.1", port: int = 8765) -> None:
    if bind not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("authoring API binds to loopback only in this version")
    server = ThreadingHTTPServer((bind, port), make_handler(service))
    print(f"GRACE Atlas Authoring API: http://{bind}:{port}")
    print("Endpoints: GET /health /settings /context?id=...; POST /translate /requirements")
    server.serve_forever()

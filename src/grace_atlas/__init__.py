# FILE: tools/grace_atlas/src/grace_atlas/__init__.py
# VERSION: 0.5.0
# START_MODULE_CONTRACT
#   PURPOSE: GRACE Atlas package — read-only projection plus optional controlled authoring workbench.
#   SCOPE: discovery, parsing, graph model, diagnostics, exports, GracePatch and optional authoring.
#   DEPENDS: stdlib only for core; authoring LLM uses OpenAI-compatible HTTP via stdlib urllib.
#   LINKS: tools/grace_atlas; M-AUTHORING-SERVICE
#   ROLE: BARREL
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   __version__ - package version string
# END_MODULE_MAP

"""GRACE Atlas — GRACE projection, traceability and controlled authoring."""

__version__ = "0.5.0"

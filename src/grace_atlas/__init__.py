# FILE: tools/grace_atlas/src/grace_atlas/__init__.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: GRACE Atlas package — read-only projection of GRACE artifacts into Obsidian Vault.
#   SCOPE: discovery, parsing, graph model, diagnostics, Obsidian export
#   DEPENDS: stdlib only (tomllib, xml.etree, pathlib, re, json, dataclasses)
#   LINKS: tools/grace_atlas
#   ROLE: BARREL
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   __version__ - package version string
# END_MODULE_MAP

"""GRACE Atlas — read-only GRACE → Obsidian Vault projector."""

__version__ = "0.2.0"


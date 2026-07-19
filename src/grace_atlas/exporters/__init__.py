# FILE: tools/grace_atlas/src/grace_atlas/exporters/__init__.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: Exporters package (lazy imports to avoid circular deps).
#   ROLE: BARREL
# END_MODULE_CONTRACT

from __future__ import annotations

from typing import Any


def export_vault(*args: Any, **kwargs: Any):
    from grace_atlas.exporters.obsidian import export_vault as _export_vault

    return _export_vault(*args, **kwargs)


__all__ = ["export_vault"]

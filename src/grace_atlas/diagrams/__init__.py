# FILE: tools/grace_atlas/src/grace_atlas/diagrams/__init__.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: User diagram catalog persistence (separate from generated snapshot diagrams).
#   SCOPE: load/save DiagramDefinition under .grace-atlas/user/diagrams
#   DEPENDS: json, pathlib
#   LINKS: Phase 3B
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""User diagram catalog helpers."""

from grace_atlas.diagrams.catalog import (
    delete_user_diagram,
    list_user_diagrams,
    load_user_diagram,
    save_user_diagram,
    user_diagrams_dir,
)

__all__ = [
    "user_diagrams_dir",
    "list_user_diagrams",
    "load_user_diagram",
    "save_user_diagram",
    "delete_user_diagram",
]

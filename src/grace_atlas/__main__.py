# FILE: tools/grace_atlas/src/grace_atlas/__main__.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Allow `python -m grace_atlas` entry.
#   SCOPE: CLI dispatch
#   DEPENDS: grace_atlas.cli
#   LINKS: tools/grace_atlas
#   ROLE: ENTRY_POINT
#   MAP_MODE: NONE
# END_MODULE_CONTRACT

from grace_atlas.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

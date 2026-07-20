# FILE: tools/grace_atlas/src/grace_atlas/roundtrip/__init__.py
# VERSION: 0.4.0
# START_MODULE_CONTRACT
#   PURPOSE: Round-trip engineering — fingerprints, drift, impact, incremental scan.
#   SCOPE: scanner, drift, impact, suggestions
#   DEPENDS: model, config, diagnostics
#   LINKS: Phase 3D
#   ROLE: BARREL
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Round-trip public API."""

from grace_atlas.roundtrip.drift import compute_drift
from grace_atlas.roundtrip.impact import impact_query
from grace_atlas.roundtrip.scanner import scan_project

__all__ = ["scan_project", "compute_drift", "impact_query"]

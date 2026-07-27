# FILE: src/grace_atlas/authoring/__init__.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Public surface of the optional authoring workbench.
#   SCOPE: exports application facade and domain request models.
#   DEPENDS: authoring.models, authoring.service, authoring.settings
#   LINKS: M-AUTHORING-DOMAIN; M-AUTHORING-SERVICE
#   ROLE: BARREL
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   AuthoringService - application facade
#   RequirementInput - requirement request
#   TranslationInput - translation request
# END_MODULE_MAP

"""Optional controlled authoring workbench for GRACE Atlas."""

from grace_atlas.authoring.models import RequirementInput, TranslationInput
from grace_atlas.authoring.service import AuthoringService
from grace_atlas.authoring.settings import AuthoringSettings, load_authoring_settings

__all__ = [
    "AuthoringService",
    "AuthoringSettings",
    "RequirementInput",
    "TranslationInput",
    "load_authoring_settings",
]

# FILE: tools/grace_atlas/src/grace_atlas/discovery.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Discover GRACE XML artifacts by known filenames and root element heuristics.
#   SCOPE: locate requirements, plan, graph, verification, packets, technology XMLs
#   DEPENDS: pathlib, xml.etree
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   GraceArtifacts - discovered artifact paths
#   discover_artifacts - scan search paths
# END_MODULE_MAP

"""GRACE artifact discovery (no assumed fixed paths beyond config)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from grace_atlas.config import AtlasConfig

# Canonical filename hints (project may use these; discovery still verifies roots).
FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "requirements": ("requirements.xml", "requirements-analysis.xml"),
    "development_plan": ("development-plan.xml", "development_plan.xml", "dev-plan.xml"),
    "knowledge_graph": ("knowledge-graph.xml", "knowledge_graph.xml", "graph.xml"),
    "verification_plan": ("verification-plan.xml", "verification_plan.xml", "verification.xml"),
    "operational_packets": ("operational-packets.xml", "operational_packets.xml", "packets.xml"),
    "technology": ("technology.xml", "technology-stack.xml", "tech-stack.xml"),
}

ROOT_HINTS: dict[str, tuple[str, ...]] = {
    "requirements": ("RequirementsAnalysis", "Requirements", "RequirementSet"),
    "development_plan": ("DevelopmentPlan",),
    "knowledge_graph": ("KnowledgeGraph",),
    "verification_plan": ("VerificationPlan",),
    "operational_packets": ("OperationalPackets",),
    "technology": ("TechnologyStack", "Technology"),
}


@dataclass
class GraceArtifacts:
    """Paths to discovered GRACE XML files (missing keys remain None)."""

    requirements: Path | None = None
    development_plan: Path | None = None
    knowledge_graph: Path | None = None
    verification_plan: Path | None = None
    operational_packets: Path | None = None
    technology: Path | None = None
    extras: list[Path] = field(default_factory=list)
    scanned_dirs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, str | list[str] | None]:
        return {
            "requirements": _rel(self.requirements),
            "development_plan": _rel(self.development_plan),
            "knowledge_graph": _rel(self.knowledge_graph),
            "verification_plan": _rel(self.verification_plan),
            "operational_packets": _rel(self.operational_packets),
            "technology": _rel(self.technology),
            "extras": [_rel(p) or str(p) for p in self.extras],
            "scanned_dirs": list(self.scanned_dirs),
        }

    def found_paths(self) -> list[Path]:
        out: list[Path] = []
        for key in (
            "requirements",
            "development_plan",
            "knowledge_graph",
            "verification_plan",
            "operational_packets",
            "technology",
        ):
            p = getattr(self, key)
            if p is not None:
                out.append(p)
        out.extend(self.extras)
        return out


def _rel(p: Path | None) -> str | None:
    if p is None:
        return None
    return str(p)


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _read_root_tag(path: Path) -> str | None:
    try:
        # Stream only the root element — large plans stay cheap to classify.
        for _event, elem in ET.iterparse(path, events=("start",)):
            return _local_tag(elem.tag)
    except (ET.ParseError, OSError, UnicodeError):
        return None
    return None


def _classify_xml(path: Path) -> str | None:
    root = _read_root_tag(path)
    if root is None:
        return None
    for kind, roots in ROOT_HINTS.items():
        if root in roots:
            return kind
    name = path.name.lower()
    for kind, names in FILENAME_HINTS.items():
        if name in names:
            return kind
    return None


def discover_artifacts(config: AtlasConfig) -> GraceArtifacts:
    """Discover GRACE XML artifacts under configured search paths."""
    result = GraceArtifacts()
    assigned: dict[str, Path] = {}

    # Explicit overrides win.
    for kind, raw in config.artifact_overrides.items():
        p = Path(raw)
        if not p.is_absolute():
            p = config.repo_root / p
        if p.is_file():
            assigned[kind] = p.resolve()

    candidates: list[Path] = []
    dirs = config.search_dirs()
    result.scanned_dirs = [str(d) for d in dirs]
    for d in dirs:
        # Prefer shallow scans: directory itself + one level of children.
        for pattern in ("*.xml", "*/*.xml"):
            for p in sorted(d.glob(pattern)):
                if p.is_file():
                    candidates.append(p.resolve())

    # Also match known filenames anywhere under search roots (bounded depth).
    for d in dirs:
        for names in FILENAME_HINTS.values():
            for name in names:
                for p in d.rglob(name):
                    # Skip deep vendor/build trees.
                    parts = set(p.parts)
                    if parts & {"node_modules", ".git", ".venv", "dist", "build", "__pycache__"}:
                        continue
                    if p.is_file():
                        candidates.append(p.resolve())

    # Deduplicate
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    for path in unique:
        kind = _classify_xml(path)
        if kind is None:
            # Keep unclassified GRACE-looking XML only if it sits next to known docs.
            if re.search(r"(grace|requirement|verification|knowledge|plan)", path.name, re.I):
                result.extras.append(path)
            continue
        if kind in assigned:
            # Prefer override; extras if another copy found.
            if assigned[kind] != path:
                result.extras.append(path)
            continue
        assigned[kind] = path

    for kind, path in assigned.items():
        if hasattr(result, kind):
            setattr(result, kind, path)

    return result

# FILE: tools/grace_atlas/src/grace_atlas/config.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Load grace-atlas.toml and resolve paths against repository root.
#   SCOPE: AtlasConfig loading via tomllib
#   DEPENDS: tomllib, pathlib, dataclasses
#   LINKS: tools/grace_atlas
#   ROLE: CONFIG
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   AtlasConfig - resolved configuration
#   load_config - load from path or defaults
# END_MODULE_MAP

"""Configuration for GRACE Atlas."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef, attr-defined]
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_SEARCH_PATHS = [".", "docs", "grace", ".grace"]
DEFAULT_SOURCE_INCLUDE = ["src/**/*.py", "tests/**/*.py", "tools/**/*.py"]
DEFAULT_SOURCE_EXCLUDE = [
    ".git/**",
    ".venv/**",
    "build/**",
    "dist/**",
    ".grace-atlas/**",
    "**/__pycache__/**",
]
DEFAULT_VAULT = ".grace-atlas/vault"
DEFAULT_HOME = "Home.md"
CONFIG_FILENAMES = ("grace-atlas.toml", ".grace-atlas.toml")


@dataclass
class AtlasConfig:
    """Resolved Atlas configuration."""

    project_name: str = "Project"
    repo_root: Path = field(default_factory=Path.cwd)
    search_paths: list[str] = field(default_factory=lambda: list(DEFAULT_SEARCH_PATHS))
    artifact_overrides: dict[str, str] = field(default_factory=dict)
    source_include: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCE_INCLUDE))
    source_exclude: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCE_EXCLUDE))
    vault_path: Path = field(default_factory=lambda: Path(DEFAULT_VAULT))
    home_note: str = DEFAULT_HOME
    vscode_enabled: bool = True
    vscode_workspace_folder: str = ""
    config_path: Path | None = None
    # diagnostics triage
    diagnostics_suppress: list[str] = field(default_factory=list)
    diagnostics_expected_patterns: list[str] = field(default_factory=list)

    def resolve_vault(self) -> Path:
        p = self.vault_path
        if not p.is_absolute():
            p = self.repo_root / p
        return p.resolve()

    def search_dirs(self) -> list[Path]:
        out: list[Path] = []
        for raw in self.search_paths:
            p = Path(raw)
            if not p.is_absolute():
                p = self.repo_root / p
            if p.is_dir():
                out.append(p.resolve())
        return out


def find_config_file(repo_root: Path) -> Path | None:
    for name in CONFIG_FILENAMES:
        candidate = repo_root / name
        if candidate.is_file():
            return candidate
    return None


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up looking for grace-atlas.toml, docs/*.xml, or .git."""
    cur = (start or Path.cwd()).resolve()
    for _ in range(12):
        if (cur / "grace-atlas.toml").is_file() or (cur / ".grace-atlas.toml").is_file():
            return cur
        if (cur / "docs" / "knowledge-graph.xml").is_file():
            return cur
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return (start or Path.cwd()).resolve()


def load_config(
    config_path: Path | None = None,
    repo_root: Path | None = None,
    vault_override: Path | None = None,
) -> AtlasConfig:
    """Load configuration from TOML or defaults."""
    root = (repo_root or find_repo_root()).resolve()
    path = config_path
    if path is None:
        path = find_config_file(root)

    data: dict[str, Any] = {}
    if path is not None and path.is_file():
        with path.open("rb") as fh:
            data = tomllib.load(fh)

    project = data.get("project") or {}
    grace = data.get("grace") or {}
    source = data.get("source") or {}
    obsidian = data.get("obsidian") or {}
    vscode = data.get("vscode") or {}
    diagnostics = data.get("diagnostics") or {}

    overrides: dict[str, str] = {}
    for key in (
        "requirements",
        "development_plan",
        "knowledge_graph",
        "verification_plan",
        "operational_packets",
        "technology",
    ):
        if grace.get(key):
            overrides[key] = str(grace[key])

    include = source.get("include")
    exclude = source.get("exclude")
    # Support duplicate [source] tables merged by user mistake: last wins in tomllib.

    vault_raw = vault_override or Path(str(obsidian.get("vault_path") or DEFAULT_VAULT))
    if not isinstance(vault_raw, Path):
        vault_raw = Path(str(vault_raw))

    return AtlasConfig(
        project_name=str(project.get("name") or root.name),
        repo_root=root,
        search_paths=list(grace.get("search_paths") or DEFAULT_SEARCH_PATHS),
        artifact_overrides=overrides,
        source_include=list(include or DEFAULT_SOURCE_INCLUDE),
        source_exclude=list(exclude or DEFAULT_SOURCE_EXCLUDE),
        vault_path=vault_raw,
        home_note=str(obsidian.get("home_note") or DEFAULT_HOME),
        vscode_enabled=bool(vscode.get("enabled", True)),
        vscode_workspace_folder=str(vscode.get("workspace_folder") or ""),
        config_path=path,
        diagnostics_suppress=[str(x) for x in (diagnostics.get("suppress") or [])],
        diagnostics_expected_patterns=[str(x) for x in (diagnostics.get("expected_patterns") or [])],
    )

# FILE: tools/grace_atlas/src/grace_atlas/bases_validate.py
# VERSION: 0.3.1
# PURPOSE: Validate generated Obsidian Bases YAML against known note properties.

"""Validate Bases files for workbench usability."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Known frontmatter / file / formula keys used in workbench notes
KNOWN_NOTE_PROPS = frozenset(
    {
        "grace_id",
        "grace_type",
        "display_name",
        "status",
        "source_state",
        "generated",
        "source_file",
        "source_line",
        "requirement_type",
        "priority",
        "parent",
        "children",
        "belongs_to_use_case",
        "implemented_by",
        "implemented_in",
        "implements",
        "depends_on",
        "dependency_of",
        "verified_by",
        "verifies",
        "tested_by",
        "planned_in",
        "evidence",
        "gap_types",
        "has_traceability_gap",
        "edge_count",
        "path",
        "module",
        "last_known_result",
        "test_files",
        "commands",
        "contracts",
        "semantic_blocks",
        "bc_parent",
        "requirement_type_note",
        "tags",
    }
)
KNOWN_FILE_PROPS = frozenset({"name", "ext", "path", "folder", "tags", "links", "size", "ctime", "mtime"})
KNOWN_FORMULAS = frozenset({"gap_flag"})


@dataclass
class BaseValidationIssue:
    path: str
    severity: str
    message: str


@dataclass
class BaseValidationReport:
    issues: list[BaseValidationIssue] = field(default_factory=list)
    bases_checked: list[str] = field(default_factory=list)
    view_names: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def validate_base_text(path: str, text: str) -> list[BaseValidationIssue]:
    issues: list[BaseValidationIssue] = []
    # Structural YAML hazards
    if re.search(r":\s*\n\s*\{\}\s*$", text, re.M) or ":\n{}" in text or ":\r\n{}" in text:
        issues.append(BaseValidationIssue(path, "error", "Empty mapping split across lines (invalid YAML)"))
    if "\t" in text:
        issues.append(BaseValidationIssue(path, "warning", "Tabs in YAML"))

    # Parse lightly with regex — full YAML optional
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except ImportError:
        data = _minimal_parse(text)
    except Exception as exc:  # noqa: BLE001
        issues.append(BaseValidationIssue(path, "error", f"YAML parse failed: {exc}"))
        return issues

    if not isinstance(data, dict):
        issues.append(BaseValidationIssue(path, "error", "Root must be mapping"))
        return issues

    views = data.get("views") or []
    names: list[str] = []
    for i, v in enumerate(views):
        if not isinstance(v, dict):
            issues.append(BaseValidationIssue(path, "error", f"views[{i}] not a mapping"))
            continue
        name = v.get("name")
        if not name:
            issues.append(BaseValidationIssue(path, "error", f"views[{i}] missing name"))
        else:
            names.append(str(name))
        order = v.get("order") or []
        for col in order:
            col_s = str(col)
            if col_s.startswith("note."):
                prop = col_s[5:]
                if prop not in KNOWN_NOTE_PROPS:
                    issues.append(
                        BaseValidationIssue(path, "error", f"Unknown note property in order: {col_s}")
                    )
            elif col_s.startswith("file."):
                prop = col_s[5:]
                if prop not in KNOWN_FILE_PROPS and prop not in {"name", "path", "folder"}:
                    issues.append(
                        BaseValidationIssue(path, "warning", f"Unusual file property: {col_s}")
                    )
            elif col_s.startswith("formula."):
                prop = col_s[8:]
                if prop not in KNOWN_FORMULAS and prop not in (data.get("formulas") or {}):
                    issues.append(
                        BaseValidationIssue(path, "warning", f"Unknown formula column: {col_s}")
                    )
            else:
                # bare property — allow if known
                if col_s not in KNOWN_NOTE_PROPS and col_s not in {"file.name"}:
                    issues.append(
                        BaseValidationIssue(
                            path,
                            "warning",
                            f"Column without note./file. prefix may not resolve: {col_s}",
                        )
                    )

    # unique view names
    seen: set[str] = set()
    for n in names:
        if n in seen:
            issues.append(BaseValidationIssue(path, "error", f"Duplicate view name: {n}"))
        seen.add(n)

    # properties keys
    props = data.get("properties") or {}
    if isinstance(props, dict):
        for key, val in props.items():
            if val is None or val == {}:
                issues.append(
                    BaseValidationIssue(path, "error", f"Empty properties entry: {key}")
                )
            if isinstance(val, dict) and not val.get("displayName") and val != {}:
                # displayName recommended
                pass
            ks = str(key)
            if ks.startswith("note.") and ks[5:] not in KNOWN_NOTE_PROPS:
                issues.append(BaseValidationIssue(path, "error", f"Unknown properties key: {ks}"))

    return issues


def _minimal_parse(text: str) -> dict[str, Any]:
    """Very small subset parser if PyYAML missing — enough for structure checks."""
    # Prefer real yaml; if missing, use regex extraction only
    views = re.findall(r"name:\s*\"([^\"]+)\"", text)
    orders = re.findall(r"^\s+-\s+(note\.[\w_]+|file\.[\w_]+|formula\.[\w_]+)$", text, re.M)
    return {
        "views": [{"name": n, "order": orders} for n in views],
        "properties": {
            m.group(1): {"displayName": "x"}
            for m in re.finditer(r"^\s+(note\.[\w_]+|file\.[\w_]+):\s*$", text, re.M)
        },
        "formulas": {},
    }


def validate_bases_dir(views_dir: Path) -> BaseValidationReport:
    report = BaseValidationReport()
    if not views_dir.is_dir():
        report.issues.append(BaseValidationIssue(str(views_dir), "error", "Views directory missing"))
        return report
    for path in sorted(views_dir.glob("*.base")):
        report.bases_checked.append(path.name)
        text = path.read_text(encoding="utf-8")
        issues = validate_base_text(path.name, text)
        report.issues.extend(issues)
        names = re.findall(r"name:\s*\"([^\"]+)\"", text)
        report.view_names[path.name] = names
    return report


def render_validation_markdown(report: BaseValidationReport) -> str:
    lines = [
        "# Bases validation",
        "",
        f"Checked: **{len(report.bases_checked)}** bases · ok={report.ok}",
        "",
    ]
    if not report.issues:
        lines.append("_No issues._")
    else:
        for i in report.issues:
            lines.append(f"- **{i.severity}** `{i.path}`: {i.message}")
    lines.append("")
    return "\n".join(lines)

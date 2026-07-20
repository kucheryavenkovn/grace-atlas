# FILE: tools/grace_atlas/src/grace_atlas/exporters/bases.py
# VERSION: 0.3.2
# PURPOSE: Generate Obsidian Bases (.base) YAML registries for the human workbench.
#
# Obsidian Bases column selection:
#   - Note frontmatter is referenced as note.<property>
#   - Columns are listed under view.order
#   - Optional properties: section sets displayName (must not be empty {})
# Docs: https://obsidian.md/help/bases/syntax

"""Obsidian Bases exporters (Views/*.base)."""

from __future__ import annotations


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _props_block(columns: list[tuple[str, str]]) -> str:
    """columns: list of (property_key, display_name).

    property_key examples: note.grace_id, file.name, formula.gap_flag
    """
    lines = ["properties:"]
    for key, display in columns:
        lines.append(f"  {key}:")
        lines.append(f"    displayName: {_q(display)}")
    return "\n".join(lines)


def _view_block(
    name: str,
    *,
    order: list[str],
    filter_kind: str | None = None,
    filter_exprs: list[str] | None = None,
    indent: int = 1,
) -> str:
    sp = "  " * indent
    lines = [
        f"{sp}- type: table",
        f"{sp}  name: {_q(name)}",
    ]
    if filter_kind and filter_exprs:
        lines.append(f"{sp}  filters:")
        lines.append(f"{sp}    {filter_kind}:")
        for e in filter_exprs:
            lines.append(f"{sp}      - {_q(e)}")
    lines.append(f"{sp}  order:")
    for col in order:
        lines.append(f"{sp}    - {col}")
    return "\n".join(lines)


# Frontmatter keys on workbench notes (see exporters/markdown.py)
NOTE_COLS = [
    ("file.name", "note"),
    ("note.grace_id", "grace_id"),
    ("note.display_name", "display_name"),
    ("note.requirement_type", "requirement_type"),
    ("note.status", "status"),
    ("note.priority", "priority"),
    ("note.has_traceability_gap", "has_traceability_gap"),
    ("note.gap_types", "gap_types"),
    ("note.source_file", "source_file"),
]

NOTE_ORDER = [k for k, _ in NOTE_COLS]


def requirements_base() -> str:
    global_filters = [
        'file.inFolder("Requirements")',
        'file.inFolder("Use-Cases")',
        'file.inFolder("Constraints")',
        'file.hasTag("grace/type/use_case")',
        'file.hasTag("grace/type/requirement")',
    ]
    # Filters on note properties use bare property names in expressions (docs examples:
    # status != "done", price > 2.1). Prefix note. is for order/properties keys.
    parts = [
        "filters:",
        "  or:",
        *[f"    - {_q(e)}" for e in global_filters],
        "formulas:",
        f"  gap_flag: {_q('if(note.has_traceability_gap, \"yes\", \"no\")')}",
        _props_block(NOTE_COLS + [("formula.gap_flag", "gap_flag")]),
        "views:",
        _view_block("Все требования", order=NOTE_ORDER),
        _view_block(
            "Бизнес-требования",
            filter_kind="and",
            filter_exprs=['note.requirement_type == "business"'],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Пользовательские требования",
            filter_kind="and",
            filter_exprs=['note.requirement_type == "user"'],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Функциональные требования",
            filter_kind="and",
            filter_exprs=['note.requirement_type == "functional"'],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Нефункциональные требования",
            filter_kind="and",
            filter_exprs=['note.requirement_type == "non_functional"'],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Пользовательские сценарии",
            filter_kind="or",
            filter_exprs=[
                'note.requirement_type == "use_case"',
                'file.inFolder("Use-Cases")',
                'file.hasTag("grace/type/use_case")',
            ],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Критерии приёмки",
            filter_kind="and",
            filter_exprs=['note.requirement_type == "acceptance_criterion"'],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Без реализации",
            filter_kind="and",
            filter_exprs=[
                "note.has_traceability_gap == true",
                'note.gap_types.contains("requirement_without_module")',
            ],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Без verification",
            filter_kind="or",
            filter_exprs=[
                'note.gap_types.contains("requirement_without_verification")',
                'note.gap_types.contains("requirement_without_verification_flow")',
            ],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Unspecified taxonomy",
            filter_kind="and",
            filter_exprs=['note.requirement_type == "unspecified"'],
            order=NOTE_ORDER,
        ),
        _view_block(
            "Базовый путь Video2PPTX",
            filter_kind="or",
            filter_exprs=[
                'file.name.contains("UC-001")',
                'file.name.contains("UC-002")',
                'file.name.contains("UC-005")',
                'file.name.contains("UC-008")',
                'file.name.contains("UC-009")',
                'file.name.contains("UC-010")',
                'file.name.contains("UC-013")',
            ],
            order=NOTE_ORDER,
        ),
    ]
    return "\n".join(parts) + "\n"


def modules_base() -> str:
    cols = [
        ("file.name", "note"),
        ("note.grace_id", "grace_id"),
        ("note.display_name", "display_name"),
        ("note.status", "status"),
        ("note.has_traceability_gap", "has_traceability_gap"),
        ("note.gap_types", "gap_types"),
        ("note.edge_count", "edge_count"),
        ("note.source_file", "source_file"),
    ]
    order = [k for k, _ in cols]
    parts = [
        "filters:",
        "  or:",
        f"    - {_q('file.inFolder(\"Modules\")')}",
        f"    - {_q('file.hasTag(\"grace/type/module\")')}",
        _props_block(cols),
        "views:",
        _view_block("Все модули", order=order),
        _view_block(
            "Без verification",
            filter_kind="and",
            filter_exprs=['note.gap_types.contains("module_without_verification")'],
            order=order,
        ),
        _view_block(
            "Без файлов",
            filter_kind="and",
            filter_exprs=['note.gap_types.contains("module_without_source")'],
            order=order,
        ),
        _view_block(
            "Без требований",
            filter_kind="and",
            filter_exprs=['note.gap_types.contains("module_without_requirement")'],
            order=order,
        ),
        _view_block(
            "С проблемами",
            filter_kind="and",
            filter_exprs=["note.has_traceability_gap == true"],
            order=order,
        ),
        _view_block("По связям", order=["note.edge_count", "note.grace_id", "file.name"]),
    ]
    return "\n".join(parts) + "\n"


def verification_base() -> str:
    cols = [
        ("file.name", "note"),
        ("note.grace_id", "grace_id"),
        ("note.status", "status"),
        ("note.module", "module"),
        ("note.has_traceability_gap", "has_traceability_gap"),
        ("note.gap_types", "gap_types"),
        ("note.last_known_result", "last_known_result"),
        ("note.source_file", "source_file"),
    ]
    order = [k for k, _ in cols]
    parts = [
        "filters:",
        "  or:",
        f"    - {_q('file.inFolder(\"Verification\")')}",
        f"    - {_q('file.hasTag(\"grace/type/verification\")')}",
        _props_block(cols),
        "views:",
        _view_block("Все проверки", order=order),
        _view_block(
            "Без тестов",
            filter_kind="and",
            filter_exprs=['note.gap_types.contains("verification_without_test")'],
            order=order,
        ),
        _view_block(
            "Без evidence",
            filter_kind="and",
            filter_exprs=['note.gap_types.contains("missing_evidence")'],
            order=order,
        ),
        _view_block(
            "Blocked",
            filter_kind="and",
            filter_exprs=['note.status == "blocked"'],
            order=order,
        ),
        _view_block(
            "Failed / in_progress",
            filter_kind="or",
            filter_exprs=['note.status == "failed"', 'note.status == "in_progress"'],
            order=order,
        ),
    ]
    return "\n".join(parts) + "\n"


def current_work_base() -> str:
    cols = [
        ("file.name", "note"),
        ("note.grace_id", "grace_id"),
        ("note.status", "status"),
        ("note.display_name", "display_name"),
        ("note.source_file", "source_file"),
    ]
    order = [k for k, _ in cols]
    parts = [
        "filters:",
        "  or:",
        f"    - {_q('file.inFolder(\"Phases\")')}",
        f"    - {_q('file.inFolder(\"Steps\")')}",
        f"    - {_q('file.inFolder(\"Operational-Packets\")')}",
        _props_block(cols),
        "views:",
        _view_block(
            "Фазы",
            filter_kind="and",
            filter_exprs=['file.inFolder("Phases")'],
            order=order,
        ),
        _view_block(
            "In progress",
            filter_kind="or",
            filter_exprs=['note.status == "in_progress"', 'note.status == "in-progress"'],
            order=order,
        ),
        _view_block(
            "Шаги",
            filter_kind="and",
            filter_exprs=['file.inFolder("Steps")'],
            order=order,
        ),
        _view_block(
            "Operational packets",
            filter_kind="and",
            filter_exprs=['file.inFolder("Operational-Packets")'],
            order=order,
        ),
    ]
    return "\n".join(parts) + "\n"


def gaps_base() -> str:
    cols = [
        ("file.name", "note"),
        ("note.grace_id", "grace_id"),
        ("note.status", "status"),
        ("note.has_traceability_gap", "has_traceability_gap"),
        ("note.gap_types", "gap_types"),
        ("note.source_file", "source_file"),
    ]
    order = [k for k, _ in cols]
    parts = [
        "filters:",
        "  or:",
        f"    - {_q('file.inFolder(\"Diagnostics\")')}",
        f"    - {_q('file.hasTag(\"grace/diagnostics\")')}",
        f"    - {_q('note.has_traceability_gap == true')}",
        _props_block(cols),
        "views:",
        _view_block(
            "Все с gaps",
            filter_kind="and",
            filter_exprs=["note.has_traceability_gap == true"],
            order=order,
        ),
        _view_block(
            "Broken / missing files",
            filter_kind="or",
            filter_exprs=[
                'note.gap_types.contains("missing_source_file")',
                'note.gap_types.contains("BROKEN_REFERENCE")',
                'note.gap_types.contains("MISSING_FILE")',
            ],
            order=order,
        ),
        _view_block(
            "Unverified modules",
            filter_kind="and",
            filter_exprs=['note.gap_types.contains("module_without_verification")'],
            order=order,
        ),
        _view_block(
            "Diagnostics notes",
            filter_kind="and",
            filter_exprs=['file.inFolder("Diagnostics")'],
            order=["file.name"],
        ),
    ]
    return "\n".join(parts) + "\n"


def source_files_base() -> str:
    cols = [
        ("file.name", "note"),
        ("note.path", "path"),
        ("note.grace_id", "grace_id"),
        ("note.has_traceability_gap", "has_traceability_gap"),
        ("note.gap_types", "gap_types"),
    ]
    order = [k for k, _ in cols]
    parts = [
        "filters:",
        "  or:",
        f"    - {_q('file.inFolder(\"Source-Files\")')}",
        f"    - {_q('file.inFolder(\"Tests\")')}",
        f"    - {_q('file.hasTag(\"grace/type/source_file\")')}",
        f"    - {_q('file.hasTag(\"grace/type/test_file\")')}",
        _props_block(cols),
        "views:",
        _view_block(
            "Source files",
            filter_kind="and",
            filter_exprs=['file.inFolder("Source-Files")'],
            order=order,
        ),
        _view_block(
            "Tests",
            filter_kind="and",
            filter_exprs=['file.inFolder("Tests")'],
            order=order,
        ),
        _view_block(
            "Missing on disk",
            filter_kind="and",
            filter_exprs=['note.gap_types.contains("missing_source_file")'],
            order=order,
        ),
    ]
    return "\n".join(parts) + "\n"


def all_bases() -> dict[str, str]:
    return {
        "Views/Requirements.base": requirements_base(),
        "Views/Modules.base": modules_base(),
        "Views/Verification.base": verification_base(),
        "Views/Current-Work.base": current_work_base(),
        "Views/Gaps.base": gaps_base(),
        "Views/Source-Files.base": source_files_base(),
    }

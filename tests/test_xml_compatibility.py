from __future__ import annotations

import warnings
from pathlib import Path

from grace_atlas.parsers._xmlutil import (
    GraceXmlCompatibilityWarning,
    parse_xml,
    sanitize_legacy_xml,
)


def test_sanitize_known_legacy_defects() -> None:
    source = r"""<Root>
  <Rule>command &lt;out&gt</Rule>
  <step-1 module=\"M-CORE\">Run</step-1>
  <scenario-1 kind="success">Done</scenario-2>
</Root>
"""
    compatible, fixes = sanitize_legacy_xml(source)
    assert "&lt;out&gt;" in compatible
    assert 'module="M-CORE"' in compatible
    assert "</scenario-1>" in compatible
    assert {fix.code for fix in fixes} == {
        "MISSING_ENTITY_SEMICOLON",
        "ESCAPED_ATTRIBUTE_QUOTE",
        "ONE_LINE_MISMATCHED_CLOSE",
    }


def test_parse_xml_reports_compatibility_warning(tmp_path: Path) -> None:
    path = tmp_path / "legacy.xml"
    path.write_text(
        "<Root>\n  <scenario-1>Done</scenario-2>\n</Root>\n",
        encoding="utf-8",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        root = parse_xml(path)
    assert root.tag == "Root"
    assert root[0].tag == "scenario-1"
    assert any(item.category is GraceXmlCompatibilityWarning for item in caught)

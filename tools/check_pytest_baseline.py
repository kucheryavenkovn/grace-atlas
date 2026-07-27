#!/usr/bin/env python3
"""Fail CI only when pytest introduces failures outside the accepted baseline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def _baseline(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _failed_node_ids(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    failed: set[str] = set()
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        classname = str(case.attrib.get("classname") or "")
        name = str(case.attrib.get("name") or "")
        if classname.startswith("tests."):
            test_path = classname.replace(".", "/") + ".py"
        else:
            test_path = classname.replace(".", "/") + ".py" if classname else ""
        # Pytest JUnit classname usually omits .py and includes tests prefix.
        node_id = f"{test_path}::{name}" if test_path else name
        failed.add(node_id)
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args(argv)

    accepted = _baseline(args.baseline)
    failed = _failed_node_ids(args.junit)
    unexpected = sorted(failed - accepted)
    resolved = sorted(accepted - failed)

    print(f"pytest failed: {len(failed)}")
    print(f"accepted baseline failures still present: {len(failed & accepted)}")
    if resolved:
        print("baseline failures now resolved (remove them from baseline):")
        for node_id in resolved:
            print(f"  RESOLVED {node_id}")
    if unexpected:
        print("unexpected failures:", file=sys.stderr)
        for node_id in unexpected:
            print(f"  NEW {node_id}", file=sys.stderr)
        return 1
    print("differential pytest gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

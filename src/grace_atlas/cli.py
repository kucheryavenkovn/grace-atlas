# FILE: tools/grace_atlas/src/grace_atlas/cli.py
# VERSION: 0.2.0
# START_MODULE_CONTRACT
#   PURPOSE: CLI for GRACE Atlas — build, status, trace, open (+ legacy aliases).
#   SCOPE: argparse entry points; no video2pptx dependency
#   DEPENDS: config, graph, diagnostics, exporters, trace, source_links
#   LINKS: tools/grace_atlas
#   ROLE: ENTRY_POINT
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""GRACE Atlas command-line interface."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import webbrowser
from pathlib import Path

from grace_atlas import __version__
from grace_atlas.config import load_config
from grace_atlas.diagnostics import build_gap_report, render_gap_report_markdown, status_counts
from grace_atlas.discovery import discover_artifacts
from grace_atlas.exporters.obsidian import VaultSafetyError, export_vault
from grace_atlas.graph import build_graph, graph_to_jsonable
from grace_atlas.source_links import obsidian_open_uri
from grace_atlas.trace import format_trace

logger = logging.getLogger("grace_atlas")


def _add_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        "--repo",
        dest="project_root",
        type=Path,
        default=None,
        help="Repository / project root (default: auto-detect)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to grace-atlas.toml",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="grace-atlas",
        description="Read-only GRACE → Obsidian Vault projector",
    )
    p.add_argument("--version", action="version", version=f"grace-atlas {__version__}")
    _add_project_root(p)
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Discover, parse, diagnose, generate Markdown + Canvas vault")
    _add_project_root(b)
    b.add_argument("--output", type=Path, default=None, help="Vault output directory")
    b.add_argument("--clean", action="store_true", default=True, help="Replace vault (default)")
    b.add_argument("--no-clean", action="store_true", help="Merge into existing vault without wipe")
    b.add_argument("--open", action="store_true", help="Open Home.md via obsidian:// URI after build")
    b.add_argument("--strict", action="store_true", help="Exit non-zero if error-severity findings exist")
    b.add_argument("--no-source", action="store_true", help="Skip source markup scan")
    b.add_argument("--verbose", action="store_true")
    b.add_argument("--json", action="store_true")

    st = sub.add_parser("status", help="Print entity/gap counters without writing vault")
    _add_project_root(st)
    st.add_argument("--no-source", action="store_true")
    st.add_argument("--json", action="store_true")
    st.add_argument("--verbose", action="store_true")

    tr = sub.add_parser("trace", help="Print traceability tree for an entity id")
    _add_project_root(tr)
    tr.add_argument("entity_id", help="Entity id, e.g. M-APP-AUTO or UC-001")
    tr.add_argument("--no-source", action="store_true")
    tr.add_argument("--verbose", action="store_true")

    op = sub.add_parser("open", help="Open generated vault Home.md via Obsidian URI")
    _add_project_root(op)
    op.add_argument("--output", type=Path, default=None, help="Vault path override")
    op.add_argument("--verbose", action="store_true")

    # Legacy / utility
    disc = sub.add_parser("discover", help="List discovered GRACE XML artifacts")
    _add_project_root(disc)
    disc.add_argument("--json", action="store_true")

    gaps = sub.add_parser("gaps", help="Print gap report markdown")
    _add_project_root(gaps)
    gaps.add_argument("--no-source", action="store_true")
    gaps.add_argument("--json", action="store_true")

    # Aliases
    gen = sub.add_parser("generate", help="Alias for build")
    _add_project_root(gen)
    gen.add_argument("--output", "--vault", dest="output", type=Path, default=None)
    gen.add_argument("--no-source", action="store_true")
    gen.add_argument("--no-clean", action="store_true")
    gen.add_argument("--open", action="store_true")
    gen.add_argument("--strict", action="store_true")
    gen.add_argument("--json", action="store_true")
    gen.add_argument("--verbose", action="store_true")

    return p


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[grace-atlas] %(levelname)s: %(message)s")


def _load(args: argparse.Namespace):
    return load_config(
        config_path=getattr(args, "config", None),
        repo_root=getattr(args, "project_root", None),
        vault_override=getattr(args, "output", None),
    )


def _try_open_vault(home: Path) -> int:
    uri = obsidian_open_uri(home)
    print(f"Opening: {uri}")
    try:
        ok = webbrowser.open(uri)
        if not ok:
            raise RuntimeError("webbrowser.open returned false")
        return 0
    except Exception as exc:  # noqa: BLE001 — user-facing soft failure
        print(f"Could not open Obsidian URI ({exc}).", file=sys.stderr)
        print(f"Vault path: {home.parent}")
        print(f"Home note:  {home}")
        print("In Obsidian: Open folder as vault → select the vault directory above.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    verbose = bool(getattr(args, "verbose", False))
    _setup_logging(verbose)

    if args.command == "discover":
        config = _load(args)
        arts = discover_artifacts(config)
        data = arts.as_dict()
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"Repo: {config.repo_root}")
            for k, v in data.items():
                print(f"  {k}: {v}")
        return 0

    if args.command == "open":
        config = _load(args)
        home = config.resolve_vault() / config.home_note
        if not home.is_file():
            print(f"Home.md not found at {home}. Run: grace-atlas build --project-root .", file=sys.stderr)
            print(f"Vault directory: {config.resolve_vault()}")
            return 1
        return _try_open_vault(home)

    include_source = not getattr(args, "no_source", False)

    if args.command == "status":
        config = _load(args)
        graph, _ = build_graph(config, include_source=include_source)
        report = build_gap_report(graph)
        counts = status_counts(graph, report)
        if getattr(args, "json", False):
            print(json.dumps(counts, indent=2, ensure_ascii=False))
        else:
            labels = [
                ("Requirements", "requirements"),
                ("Modules", "modules"),
                ("Source files", "source_files"),
                ("Verification records", "verification_records"),
                ("Tests", "tests"),
                ("Edges", "edges"),
                ("Broken references", "broken_references"),
                ("Orphan requirements", "orphan_requirements"),
                ("Unverified modules", "unverified_modules"),
                ("Unmapped files", "unmapped_files"),
            ]
            for label, key in labels:
                print(f"{label:24} {counts[key]}")
        return 0

    if args.command == "trace":
        config = _load(args)
        graph, _ = build_graph(config, include_source=include_source)
        sys.stdout.write(format_trace(graph, args.entity_id))
        return 0

    if args.command == "gaps":
        config = _load(args)
        graph, _ = build_graph(config, include_source=include_source)
        report = build_gap_report(graph)
        if getattr(args, "json", False):
            print(json.dumps({"summary": report.summary}, indent=2, ensure_ascii=False))
        else:
            print(render_gap_report_markdown(report))
        return 0

    if args.command in {"build", "generate"}:
        config = _load(args)
        graph, arts = build_graph(config, include_source=include_source)
        report = build_gap_report(graph)
        clean = not getattr(args, "no_clean", False)
        try:
            result = export_vault(graph, config, clean=clean, report=report)
        except VaultSafetyError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Vault: {result['vault']}")
            print(f"Nodes: {result['nodes']}  Edges: {result['edges']}  Notes: {result.get('notes_written')}")
            print(f"Generated at: {result.get('generated_at')}")
            gaps = result.get("gaps") or {}
            print(f"Findings: {gaps.get('findings')}  {gaps.get('by_severity')}")
            miss = result.get("missing_canvas_refs") or []
            if miss:
                print(f"Canvas missing note refs: {len(miss)} (sample: {miss[:3]})")
            print("Open vault in Obsidian (Open folder as vault). Use: python -m grace_atlas open")

        if getattr(args, "open", False):
            home = Path(result["vault"]) / config.home_note
            _try_open_vault(home)

        if getattr(args, "strict", False):
            errors = (report.summary.get("by_severity") or {}).get("error", 0)
            if errors:
                print(f"strict: {errors} error findings", file=sys.stderr)
                return 1
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

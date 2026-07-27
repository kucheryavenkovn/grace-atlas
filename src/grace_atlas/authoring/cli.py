# FILE: src/grace_atlas/authoring/cli.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Standalone CLI for authoring settings, context, translation, requirements and local API.
#   SCOPE: argparse interface; source mutation remains delegated to grace-atlas patch plan/validate/apply.
#   DEPENDS: config, authoring service/api/models/settings
#   LINKS: M-AUTHORING-CLI
#   ROLE: ENTRY_POINT
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
# START_MODULE_MAP
#   main - grace-atlas-author command entry point
# END_MODULE_MAP

"""Standalone authoring CLI, intentionally separate from the read-only projector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from grace_atlas.authoring.api import serve_authoring_api
from grace_atlas.authoring.models import RequirementInput, TranslationInput
from grace_atlas.authoring.patching import apply_authoring_patch, plan_authoring_patch, validate_authoring_patch
from grace_atlas.authoring.service import AuthoringService
from grace_atlas.authoring.settings import render_settings_template
from grace_atlas.config import load_config


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", "--repo", dest="project_root", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grace-atlas-author",
        description="Controlled authoring, translation and requirement drafting for GRACE Atlas",
    )
    _common(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    settings = sub.add_parser("settings", help="Show effective authoring settings or write a safe template")
    _common(settings)
    settings.add_argument("--init", action="store_true", help="Write grace-atlas.authoring.example.toml")
    settings.add_argument("--output", type=Path, default=None)

    context = sub.add_parser("context", help="Build minimal traceable context for one or more entity IDs")
    _common(context)
    context.add_argument("entity_ids", nargs="+")
    context.add_argument("--depth", type=int, default=None)
    context.add_argument("--max-nodes", type=int, default=None)
    context.add_argument("--output", type=Path, default=None)

    translate = sub.add_parser("translate", help="Create translation sidecar and optional source-replacement patch")
    _common(translate)
    translate.add_argument("entity_id")
    translate.add_argument("--target-language", default=None)
    translate.add_argument("--source-language", default=None)
    translate.add_argument("--fields", default=None, help="Comma-separated node fields")
    translate.add_argument("--replace-source", action="store_true")

    requirement = sub.add_parser("requirement", help="Draft a traceable UC and generate GracePatch")
    _common(requirement)
    requirement.add_argument("--from", dest="evidence_ids", nargs="+", required=True)
    requirement.add_argument("--id", dest="requirement_id", default="")
    requirement.add_argument("--title", default="")
    requirement.add_argument("--actor", default="")
    requirement.add_argument("--action", default="")
    requirement.add_argument("--goal", default="")
    requirement.add_argument("--acceptance", action="append", default=[])
    requirement.add_argument("--precondition", action="append", default=[])
    requirement.add_argument("--priority", default="medium")
    requirement.add_argument("--related-flows", default="")
    requirement.add_argument("--no-llm", action="store_true")

    patch = sub.add_parser("patch", help="Plan, validate or apply an authoring-generated GracePatch")
    patch_sub = patch.add_subparsers(dest="patch_command", required=True)
    for name in ("plan", "validate", "apply"):
        command = patch_sub.add_parser(name)
        _common(command)
        command.add_argument("patch_file", type=Path)
        if name == "apply":
            command.add_argument("--confirm", action="store_true")

    serve = sub.add_parser("serve", help="Start loopback JSON API for a future GUI")
    _common(serve)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    return parser


def _service(args: argparse.Namespace) -> AuthoringService:
    config = load_config(config_path=getattr(args, "config", None), repo_root=getattr(args, "project_root", None))
    return AuthoringService(config)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        service = _service(args)
        if args.command == "settings":
            if args.init:
                output = args.output or (service.config.repo_root / "grace-atlas.authoring.example.toml")
                if output.exists():
                    raise FileExistsError(output)
                output.write_text(render_settings_template(), encoding="utf-8", newline="\n")
                print(output)
            else:
                print(json.dumps(service.settings.public_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "context":
            result = service.context(args.entity_ids, depth=args.depth, max_nodes=args.max_nodes)
            text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="utf-8")
                print(args.output)
            else:
                print(text, end="")
            return 0

        if args.command == "translate":
            result = service.translate(
                TranslationInput(
                    entity_id=args.entity_id,
                    target_language=args.target_language or service.settings.translation.default_target_language,
                    source_language=args.source_language or service.settings.translation.default_source_language,
                    fields=_csv(args.fields) if args.fields else service.settings.translation.fields,
                    replace_source=bool(args.replace_source),
                )
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0

        if args.command == "requirement":
            result = service.requirement(
                RequirementInput(
                    evidence_ids=tuple(args.evidence_ids),
                    requirement_id=args.requirement_id,
                    title=args.title,
                    actor=args.actor,
                    action=args.action,
                    goal=args.goal,
                    acceptance_criteria=tuple(args.acceptance),
                    preconditions=tuple(args.precondition),
                    priority=args.priority,
                    related_flows=_csv(args.related_flows),
                    use_llm=not args.no_llm,
                )
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0

        if args.command == "patch":
            if args.patch_command == "plan":
                result = plan_authoring_patch(service.config, args.patch_file).as_dict()
            elif args.patch_command == "validate":
                result = validate_authoring_patch(service.config, args.patch_file)
            else:
                result = apply_authoring_patch(
                    service.config, args.patch_file, confirm=bool(args.confirm), workspace=service.settings.workspace
                )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0 if result.get("ok") else 1

        if args.command == "serve":
            serve_authoring_api(service, bind=args.bind, port=args.port)
            return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

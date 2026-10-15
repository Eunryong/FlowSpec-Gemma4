from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import Config
from .research_runner import ExperimentRunner, check_environment
from .research_store import DEFAULT_RESEARCH_ROOT, ResearchError


def _common(parser: argparse.ArgumentParser, *, needs_run_inputs: bool = False) -> None:
    parser.add_argument("--research-root", default=str(DEFAULT_RESEARCH_ROOT))
    parser.add_argument("--model", help="Model identifier (defaults to LLAMA_MODEL)")
    parser.add_argument("--base-url", help="llama.cpp OpenAI-compatible base URL")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--context-length", type=int)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--max-steps", type=int)
    if needs_run_inputs:
        parser.add_argument("--track", required=True, choices=("track1", "track2"))
        parser.add_argument("--condition", required=True)
        parser.add_argument("--brief", required=True)
        parser.add_argument("--task-id")
        parser.add_argument("--source-workspace")
        parser.add_argument("--server-config", help="Human-readable server/build configuration label")
        parser.add_argument("--fixed-design", help="Optional path to a fixed design_spec.json to bypass Stage 1")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="run-experiment",
        description="File-based, condition-controlled Gemma coding-agent research harness",
    )
    commands = root.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="Check directories, schema, dependencies, and llama.cpp health")
    _common(check)

    for name, help_text in (
        ("design", "Run only the fresh Designer stage"),
        ("full", "Run Designer then a fresh Coder stage"),
        ("direct", "Run direct Coder stage without upfront Designer stage"),
    ):
        run = commands.add_parser(name, help=help_text)
        _common(run, needs_run_inputs=True)
        run.add_argument("--repetitions", type=int, default=1)

    show = commands.add_parser("show", help="Print one run's metadata")
    _common(show)
    show.add_argument("run_id")

    listing = commands.add_parser("list", help="List run metadata")
    _common(listing)
    listing.add_argument("--track", choices=("track1", "track2"))

    verify = commands.add_parser("verify-group", help="Verify common brief/condition hashes")
    _common(verify)
    verify.add_argument("--track", required=True, choices=("track1", "track2"))
    verify.add_argument("--condition")

    export = commands.add_parser("export", help="Export comparison metrics as JSON or CSV")
    _common(export)
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=("json", "csv"), default="json")
    export.add_argument("--track", choices=("track1", "track2"))

    blind = commands.add_parser("blind-export", help="Export condition-blinded evaluation artifacts")
    _common(blind)
    blind.add_argument("--run-id", action="append", dest="run_ids")
    blind.add_argument("--output-root")

    revise = commands.add_parser("revise", help="Reveal the next Track 2 change after V1 completes")
    _common(revise)
    revise.add_argument("run_id")
    return root


def _config(args: argparse.Namespace) -> Config:
    base = Config()
    updates: dict[str, Any] = {}
    for argument, field in (
        ("model", "model"),
        ("base_url", "base_url"),
        ("temperature", "temperature"),
        ("seed", "seed"),
        ("context_length", "context_length"),
        ("max_output_tokens", "max_tokens"),
        ("timeout", "timeout_seconds"),
        ("max_steps", "max_steps"),
    ):
        value = getattr(args, argument, None)
        if value is not None:
            updates[field] = value
    return replace(base, **updates)


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Convenient shorthand matching the originally requested invocation:
    # run-experiment --track ... --condition ... defaults to a full run.
    if arguments and arguments[0].startswith("--") and arguments[0] not in {"-h", "--help"}:
        arguments.insert(0, "full")
    args = parser().parse_args(arguments)
    config = _config(args)
    try:
        if args.command == "check":
            result = check_environment(args.research_root, config)
            _print_json(result)
            return 0 if result["ready"] else 1

        runner = ExperimentRunner(
            args.research_root,
            config=config,
            source_workspace=getattr(args, "source_workspace", None),
            server_config=getattr(args, "server_config", None),
        )
        if args.command in {"design", "full", "direct"}:
            if args.command == "design":
                method = runner.run_design
            elif args.command == "direct":
                method = runner.run_direct
            else:
                method = runner.run_full
            result = method(
                track=args.track,
                condition=args.condition,
                brief=args.brief,
                repetitions=args.repetitions,
                seed=args.seed,
                task_id=args.task_id,
                fixed_design=getattr(args, "fixed_design", None),
            )
        elif args.command == "show":
            result = runner.show(args.run_id)
        elif args.command == "list":
            result = runner.list_metadata(track=args.track)
        elif args.command == "verify-group":
            result = runner.verify_group(track=args.track, condition=args.condition)
        elif args.command == "export":
            result = {"output": str(runner.export_comparison(
                output=args.output, format=args.format, track=args.track
            ))}
        elif args.command == "blind-export":
            output, mapping = runner.blind_export(args.run_ids, args.output_root)
            result = {"output": str(output), "mapping_saved_under_hidden": True,
                      "anonymous_ids": sorted(mapping)}
        elif args.command == "revise":
            result = runner.revise(args.run_id)
        else:
            raise ResearchError(f"Unsupported command: {args.command}")
        _print_json(result)
        return 0
    except (ResearchError, OSError, ValueError) as exc:
        print(f"run-experiment: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import CodingAgent
from .config import Config


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Minimal Gemma coding-agent harness for llama.cpp")
    p.add_argument("--workspace", required=True, help="Directory the agent may read/write")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--prompt", help="One-shot task")
    mode.add_argument(
        "--interactive",
        action="store_true",
        help="Run a persistent interactive session (the default when --prompt is omitted)",
    )
    p.add_argument("--system-prompt", help="Optional path to a custom system prompt")
    p.add_argument("--trace", help="Optional JSONL trace output path")
    p.add_argument("--run-id", help="Optional run identifier stored in the trace")
    p.add_argument("--task-id", help="Optional task label stored in the trace")
    p.add_argument("--condition", help="Optional condition label stored in the trace only")
    p.add_argument("--stage", help="Optional stage label stored in the trace only")
    return p


def main() -> None:
    args = parser().parse_args()
    system_prompt = None
    if args.system_prompt:
        system_prompt = Path(args.system_prompt).read_text(encoding="utf-8")

    kwargs = {
        "workspace_path": args.workspace,
        "config": Config(),
        "trace_path": args.trace,
        "run_id": args.run_id,
        "trace_metadata": {
            "task_id": args.task_id,
            "condition": args.condition,
            "stage": args.stage,
        },
    }
    if system_prompt is not None:
        kwargs["system_prompt"] = system_prompt
    agent = CodingAgent(**kwargs)

    if args.prompt is not None:
        print(agent.run(args.prompt))
        return

    print("Gemma agent ready. Type 'exit' or 'quit' to quit.")
    while True:
        try:
            text = input("gemma> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in {"exit", "quit"}:
            break
        if not text:
            continue
        try:
            response = agent.run(text)
        except KeyboardInterrupt:
            print()
            break
        except Exception as exc:
            print(f"error> {type(exc).__name__}: {exc}")
        else:
            print("agent>", response)

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from src.ast import parse_program
from src.runtime import Runtime
from src.trace import JSONLTracer


def _read_program_source(path: str) -> str:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    return target.read_text()


def _add_tracer(runtime: Runtime, destination: str):
    sink = open(destination, "w", encoding="utf-8")
    tracer = JSONLTracer(sink)
    runtime.event_hooks.append(tracer)
    return sink


def run_cli(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Nanocode program from an S-expression file.")
    parser.add_argument("program", help="Path to the Nanocode program (S-expression format)")
    parser.add_argument("--trace-jsonl", dest="trace_jsonl", help="Write runtime events to a JSONL file")
    parser.add_argument(
        "--max-steps",
        dest="max_steps",
        type=int,
        help="Override the program step budget (applies to this invocation only)",
    )
    parser.add_argument(
        "--steps-only",
        action="store_true",
        help="Run for the max-steps budget without waiting for the scheduler to idle",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    sink = None

    try:
        src = _read_program_source(args.program)
        program = parse_program(src)
        if args.max_steps is not None:
            program = replace(program, max_steps=args.max_steps)

        runtime = Runtime(program.rules)
        sink = _add_tracer(runtime, args.trace_jsonl) if args.trace_jsonl else None

        runtime.load(program.root)
        if args.steps_only:
            runtime.run(max_steps=program.max_steps)
        else:
            runtime.run_until_idle(max_steps=program.max_steps)

        summary = {
            "program": program.name,
            "root": runtime.root_id,
            "events": len(runtime.events),
            "frontier": list(runtime.scheduler.pending()),
            "store_size": len(runtime.store),
        }

        print(json.dumps(summary, indent=2))
        return 0
    except Exception as exc:  # pragma: no cover - defensive shell entry
        print(f"nanocode: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.trace_jsonl and sink is not None:
            sink.close()


def main() -> int:  # pragma: no cover - thin wrapper
    return run_cli()


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())

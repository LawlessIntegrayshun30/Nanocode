from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Optional

from src.ast import parse_program
from src.runtime import Runtime
from src.scheduler import FIFOScheduler, LIFOScheduler
from src.trace import JSONLTracer
from src.term_store import TermStore


def _read_program_source(path: str) -> str:
    """Load program text from a file path or stdin.

    Passing ``-`` reads from stdin to support piping programs into the CLI.
    """

    if path == "-":
        return sys.stdin.read()

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    return target.read_text()


def _add_tracer(runtime: Runtime, destination: str):
    sink = open(destination, "w", encoding="utf-8")
    tracer = JSONLTracer(sink)
    runtime.event_hooks.append(tracer)
    return sink


def _load_store(path: str) -> dict:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)

    return json.loads(target.read_text())


def _resolve_scheduler(choice: Optional[str]) -> str:
    if choice is None:
        return "fifo"
    return choice


def _parse_rule_budgets(entries: Optional[Iterable[str]]) -> Optional[dict[str, int]]:
    """Translate CLI ``--rule-budget name=N`` entries into a mapping."""

    if not entries:
        return None

    budgets: dict[str, int] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Rule budget must be name=N: {entry}")
        name, raw = entry.split("=", 1)
        if not name:
            raise ValueError("Rule budget name cannot be empty")
        limit = int(raw)
        if limit <= 0:
            raise ValueError(f"Rule budget for {name} must be positive")
        budgets[name] = limit

    return budgets


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
    parser.add_argument(
        "--walk-children",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Automatically schedule child terms for rewriting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the program (and optional snapshot) without executing rewrites",
    )
    parser.add_argument(
        "--strict-matching",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Fail fast if multiple rules match the same term instead of picking the first",
    )
    parser.add_argument(
        "--store-json",
        dest="store_json",
        help="Write the term store snapshot to a JSON file for replay/inspection",
    )
    parser.add_argument(
        "--load-store",
        dest="load_store",
        help="Bootstrap the runtime from a prior store snapshot (JSON)",
    )
    parser.add_argument(
        "--scheduler",
        choices=("fifo", "lifo"),
        default=None,
        help="Choose the rewrite scheduling strategy (fifo or lifo)",
    )
    parser.add_argument(
        "--rule-budget",
        action="append",
        dest="rule_budgets",
        help="Limit how many times a rule may fire (name=N, can repeat)",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    sink = None

    try:
        src = _read_program_source(args.program)
        program = parse_program(src)
        if args.max_steps is not None:
            program = replace(program, max_steps=args.max_steps)

        state = _load_store(args.load_store) if args.load_store else None
        scheduler_choice = _resolve_scheduler(args.scheduler or (state.get("scheduler") if state else None))
        scheduler = FIFOScheduler() if scheduler_choice == "fifo" else LIFOScheduler()
        walk_children = args.walk_children
        strict_matching = args.strict_matching
        state_budgets = state.get("rule_budgets") if state else None
        rule_budgets = _parse_rule_budgets(args.rule_budgets)
        if state:
            if walk_children is None:
                walk_children = bool(state.get("walk_children", False))
            if strict_matching is None:
                strict_matching = bool(state.get("strict_matching", False))
            if rule_budgets is None:
                rule_budgets = dict(state_budgets) if state_budgets else None
        if walk_children is None:
            walk_children = False
        if strict_matching is None:
            strict_matching = False
        if rule_budgets is None:
            rule_budgets = {}
        runtime = Runtime(
            program.rules,
            scheduler=scheduler,
            walk_children=walk_children,
            strict_matching=strict_matching,
            rule_budgets=rule_budgets,
        )
        sink = _add_tracer(runtime, args.trace_jsonl) if args.trace_jsonl else None
        if state:
            store = TermStore.from_json(state)
            frontier = state.get("frontier") if isinstance(state, dict) else None
            processed = state.get("processed") if isinstance(state, dict) else None
            exhausted = state.get("rule_budget_exhausted") if isinstance(state, dict) else None
            root_id = state.get("root") if isinstance(state, dict) else None
            if root_id is None:
                raise ValueError("Store snapshot is missing a root term id")
            runtime.load_state(
                store=store,
                root_id=root_id,
                frontier=frontier,
                processed=processed,
                rule_budgets=rule_budgets,
                rule_budget_exhausted=exhausted,
            )
        else:
            runtime.load(program.root)
        if args.dry_run:
            stats = runtime.stats()
        else:
            if args.steps_only:
                runtime.run(max_steps=program.max_steps)
            else:
                runtime.run_until_idle(max_steps=program.max_steps)

            stats = runtime.stats()
        summary = {
            "program": program.name,
            "root": runtime.root_id,
            "dry_run": args.dry_run,
            "walk_children": runtime.walk_children,
            "strict_matching": runtime.strict_matching,
            "scheduler": runtime._scheduler_name(),
            "rule_budgets": runtime.rule_budgets,
            **stats,
        }

        if args.store_json:
            store_path = Path(args.store_json)
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store_path.write_text(json.dumps(runtime.store.to_bundle(
                root=runtime.root_id,
                frontier=runtime.scheduler.pending(),
                scheduler=scheduler_choice,
                processed=runtime._processed,
                walk_children=runtime.walk_children,
                strict_matching=runtime.strict_matching,
                rule_budgets=runtime.rule_budgets,
                rule_budget_exhausted=runtime.rule_budget_exhausted,
            ), indent=2))

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

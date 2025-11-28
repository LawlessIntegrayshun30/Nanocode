from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Optional

from src.ast import parse_program
from src.runtime import Runtime
from src.scheduler import FIFOScheduler, LIFOScheduler, RandomScheduler
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
    if choice not in {"fifo", "lifo", "random"}:
        raise ValueError(f"Unsupported scheduler: {choice}")
    return choice


def _build_scheduler(choice: str, *, seed: int | None = None, state: object | None = None):
    def _coerce_state(payload: object | None) -> object | None:
        if isinstance(payload, list):
            return tuple(_coerce_state(item) for item in payload)
        if isinstance(payload, tuple):
            return tuple(_coerce_state(item) for item in payload)
        return payload

    if choice == "lifo":
        return LIFOScheduler()
    if choice == "random":
        return RandomScheduler(seed=seed, state=_coerce_state(state))
    return FIFOScheduler()


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
        "--walk-depth",
        dest="walk_depth",
        type=int,
        help="Limit how deep child-walking recurses (applies when walk-children is enabled)",
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
        choices=("fifo", "lifo", "random"),
        default=None,
        help="Choose the rewrite scheduling strategy (fifo, lifo, or random)",
    )
    parser.add_argument(
        "--scheduler-seed",
        dest="scheduler_seed",
        type=int,
        help="Seed for the random scheduler (ignored for fifo/lifo)",
    )
    parser.add_argument(
        "--max-terms",
        dest="max_terms",
        type=int,
        help="Limit how many terms may be stored before halting",
    )
    parser.add_argument(
        "--rule-budget",
        action="append",
        dest="rule_budgets",
        help="Limit how many times a rule may fire (name=N, can repeat)",
    )
    parser.add_argument(
        "--only-rule",
        action="append",
        dest="include_rules",
        help="Restrict execution to the specified rule(s) (can repeat)",
    )
    parser.add_argument(
        "--skip-rule",
        action="append",
        dest="exclude_rules",
        help="Exclude the specified rule(s) from execution (can repeat)",
    )
    parser.add_argument(
        "--only-scale",
        action="append",
        dest="include_scales",
        type=int,
        help="Restrict execution to terms at the specified scale(s) (can repeat)",
    )
    parser.add_argument(
        "--skip-scale",
        action="append",
        dest="exclude_scales",
        type=int,
        help="Exclude terms at the specified scale(s) from execution (can repeat)",
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
        scheduler_seed = args.scheduler_seed if args.scheduler_seed is not None else (state.get("scheduler_seed") if state else None)
        scheduler_state = state.get("scheduler_state") if state else None
        scheduler = _build_scheduler(scheduler_choice, seed=scheduler_seed, state=scheduler_state)
        walk_children = args.walk_children
        strict_matching = args.strict_matching
        state_budgets = state.get("rule_budgets") if state else None
        rule_budgets = _parse_rule_budgets(args.rule_budgets)
        state_max_terms = state.get("max_terms") if state else None
        max_terms = args.max_terms if args.max_terms is not None else state_max_terms
        if max_terms is not None and max_terms <= 0:
            raise ValueError("max_terms must be positive")
        state_walk_depth = state.get("walk_depth") if state else None
        walk_depth = args.walk_depth if args.walk_depth is not None else state_walk_depth
        if walk_depth is not None and walk_depth <= 0:
            raise ValueError("walk_depth must be positive")
        include_rules = args.include_rules if args.include_rules is not None else None
        exclude_rules = args.exclude_rules if args.exclude_rules is not None else None
        include_scales = args.include_scales if args.include_scales is not None else None
        exclude_scales = args.exclude_scales if args.exclude_scales is not None else None
        if state:
            if include_rules is None and "include_rules" in state:
                include_rules = state.get("include_rules")
            if exclude_rules is None and "exclude_rules" in state:
                exclude_rules = state.get("exclude_rules")
            if include_scales is None and "include_scales" in state:
                include_scales = state.get("include_scales")
            if exclude_scales is None and "exclude_scales" in state:
                exclude_scales = state.get("exclude_scales")
        if include_rules and exclude_rules:
            overlap = set(include_rules) & set(exclude_rules)
            if overlap:
                raise ValueError(f"Rules cannot be both included and excluded: {sorted(overlap)}")
        if include_scales and exclude_scales:
            overlap = set(include_scales) & set(exclude_scales)
            if overlap:
                raise ValueError(f"Scales cannot be both included and excluded: {sorted(overlap)}")
        rule_names = {rule.name for rule in program.rules}
        if include_rules:
            missing = set(include_rules) - rule_names
            if missing:
                raise ValueError(f"Included rules not found: {sorted(missing)}")
        if exclude_rules:
            missing = set(exclude_rules) - rule_names
            if missing:
                raise ValueError(f"Excluded rules not found: {sorted(missing)}")
        for scale in (include_scales or []) + (exclude_scales or []):
            if scale < 0:
                raise ValueError("Scale filters must be non-negative")
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
            walk_depth=walk_depth,
            strict_matching=strict_matching,
            rule_budgets=rule_budgets,
            max_terms=max_terms,
            include_rules=include_rules,
            exclude_rules=exclude_rules,
            include_scales=include_scales,
            exclude_scales=exclude_scales,
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
                scheduler_state=scheduler_state,
                include_rules=include_rules,
                exclude_rules=exclude_rules,
                include_scales=include_scales,
                exclude_scales=exclude_scales,
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
            "walk_depth": runtime.walk_depth,
            "strict_matching": runtime.strict_matching,
            "scheduler": runtime._scheduler_name(),
            "scheduler_seed": getattr(runtime.scheduler, "seed", None),
            "rule_budgets": runtime.rule_budgets,
            "max_terms": runtime.max_terms,
            "include_rules": sorted(runtime.include_rules) if runtime.include_rules else None,
            "exclude_rules": sorted(runtime.exclude_rules) if runtime.exclude_rules else [],
            "include_scales": sorted(runtime.include_scales) if runtime.include_scales else None,
            "exclude_scales": sorted(runtime.exclude_scales) if runtime.exclude_scales else [],
            **stats,
        }

        if args.store_json:
            store_path = Path(args.store_json)
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store_path.write_text(json.dumps(runtime.store.to_bundle(
                root=runtime.root_id,
                frontier=runtime.scheduler.pending(),
                scheduler=scheduler_choice,
                scheduler_seed=getattr(runtime.scheduler, "seed", None),
                scheduler_state=runtime.scheduler.state() if hasattr(runtime.scheduler, "state") else None,
                processed=runtime._processed,
                walk_children=runtime.walk_children,
                walk_depth=runtime.walk_depth,
                strict_matching=runtime.strict_matching,
                rule_budgets=runtime.rule_budgets,
                rule_budget_exhausted=runtime.rule_budget_exhausted,
                max_terms=runtime.max_terms,
                term_limit_exhausted=runtime.term_limit_exhausted,
                include_rules=runtime.include_rules,
                exclude_rules=runtime.exclude_rules,
                include_scales=runtime.include_scales,
                exclude_scales=runtime.exclude_scales,
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

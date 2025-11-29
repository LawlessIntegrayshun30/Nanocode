"""Prototype demo runner to exercise micro/meso/macro flows end-to-end."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Tuple

from src.bridge import BridgeBinding, BridgePort, BridgeSchema, bridge_call_action, validate_bridge_schema
from src.interpreter import Execution, Interpreter, Program, validate_program
from src.rewrite import Pattern, Rule, expand_action, lift_action, reduce_action
from src.runtime import Runtime
from src.term_store import TermStore
from src.terms import Term, term_to_dict
from src.trace import JSONLTracer


VOWELS = set("aeiouAEIOU")


def _leaves(term: Term) -> Iterable[Term]:
    stack = [term]
    while stack:
        node = stack.pop()
        if not node.children:
            yield node
            continue
        stack.extend(reversed(node.children))


def _motif_summary(children: list[Term]) -> str:
    """Summarize motif payloads for reduction provenance."""

    labels = [child.sym for child in children]
    counts = Counter(labels)
    dominant, freq = counts.most_common(1)[0]
    return f"dominant={dominant};freq={freq};span={len(labels)}"


def _macro_binding(text: str) -> Tuple[BridgeBinding, Callable[[Term], object]]:
    schema = validate_bridge_schema(
        BridgeSchema(
            name="prototype-macro",
            ports=(BridgePort(name="macro", direction="out", scale=2, description="macro label"),),
            metadata={"demo": True},
        )
    )

    vowels = sum(1 for ch in text if ch in VOWELS)
    consonants = len(text) - vowels

    def _macro_label(_term: Term) -> str:
        if not text:
            return "empty"
        ratio = vowels / len(text)
        balance = "vowel-heavy" if ratio > 0.6 else "consonant-heavy" if ratio < 0.4 else "mixed"
        return f"{balance};len={len(text)};v={vowels};c={consonants}"

    def _encode(payload: object) -> Term:
        port = schema.port("macro")
        return Term(sym=str(payload), scale=port.scale or 0)

    binding = BridgeBinding(schema=schema, encode={"macro": _encode}, decode={"macro": lambda t: t.sym})
    return binding, _macro_label


def _tokenize(text: str) -> list[Term]:
    return [Term(sym=ch, scale=0) for ch in text]


def make_prototype_program(text: str) -> Program:
    """Build a deterministic micro→meso→macro program for the demo."""

    binding, oracle = _macro_binding(text)
    root = Term(sym="text", scale=0, children=_tokenize(text))

    def has_summary(term: Term) -> bool:
        return any(child.sym.startswith("summary:") for child in term.children)

    def is_expand_target(term: Term) -> bool:
        return term.sym == "text" and term.scale == 0 and not has_summary(term)

    rules = [
        Rule(name="expand-meso", pattern=Pattern(predicate=is_expand_target), action=expand_action(fanout=3)),
        Rule(name="reduce-text", pattern=Pattern(predicate=lambda t: t.sym.startswith("F(text")), action=reduce_action(summarizer=_motif_summary)),
        Rule(name="lift-summary", pattern=Pattern(predicate=has_summary), action=lift_action()),
        Rule(name="classify", pattern=Pattern(predicate=lambda t: t.sym.startswith("lift[text")), action=bridge_call_action(binding, "macro", oracle)),
    ]

    program = Program(name="prototype-demo", root=root, rules=rules, max_steps=128)
    validate_program(program)
    return program


def run_prototype(text: str, trace: Path | None = None, store: Path | None = None) -> Execution:
    program = make_prototype_program(text)
    runtime = Runtime(program.rules, walk_children=True, detect_conflicts=True)
    trace_sink = None
    if trace:
        trace_sink = trace.open("w", encoding="utf-8")
        runtime.event_hooks.append(JSONLTracer(trace_sink))

    root_id = runtime.load(program.root)
    runtime.run_until_idle(max_steps=program.max_steps)

    snapshot = runtime.snapshot()
    stats = runtime.stats()
    if trace_sink:
        trace_sink.close()

    if store:
        payload = {
            "store": runtime.store.to_json(),
            "root": snapshot["root"],
            "frontier": snapshot["frontier"],
            "processed": list(snapshot["processed"]),
        }
        store.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return Execution(program=program, root_id=root_id, events=list(runtime.events), snapshot=snapshot, stats=stats)


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Run the Nanocode prototype demo end-to-end")
    parser.add_argument("--text", required=True, help="Input text to classify")
    parser.add_argument("--trace-jsonl", type=Path, help="Optional JSONL trace output path")
    parser.add_argument("--store-json", type=Path, help="Optional term store snapshot path")
    args = parser.parse_args()

    execution = run_prototype(args.text, trace=args.trace_jsonl, store=args.store_json)
    final_term = execution.materialize_root()

    macro = next(child for child in final_term.children if child.sym.startswith("port:out:macro"))
    macro_label = macro.children[0].sym

    summary = {
        "program": execution.program.name,
        "input": args.text,
        "final_term": term_to_dict(final_term),
        "macro_label": macro_label,
        "trace": str(args.trace_jsonl) if args.trace_jsonl else None,
        "store": str(args.store_json) if args.store_json else None,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    _cli()

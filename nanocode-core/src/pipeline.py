"""Pipeline expressed purely as Nanocode terms and rewrite rules.

This module replaces the ad hoc Python pipeline with a Program that
materializes micro/meso/macro terms and runs through the runtime so the
entire workflow is traceable and evolvable.
"""

from __future__ import annotations

from collections import Counter
from typing import List

from src.interpreter import Program
from src.rewrite import Pattern, Rule, expand_action, reduce_action
from src.terms import Term


def _tokenize(text: str) -> List[Term]:
    return [Term(sym=ch, scale=0) for ch in text]


def _meso_summary(children: List[Term]) -> str:
    def _normalize(sym: str) -> str:
        if sym.startswith("motif[") and sym.endswith("]"):
            payload = sym[len("motif[") : -1]
            return payload.replace("|", "")
        return sym

    counts = Counter(_normalize(child.sym) for child in children)
    if not counts:
        return "empty"
    dominant, freq = counts.most_common(1)[0]
    return f"dominant={dominant};freq={freq}"


def make_text_program(text: str) -> Program:
    """Construct a multi-scale program that mirrors the original pipeline."""

    root = Term(sym="text", scale=0, children=_tokenize(text))

    def is_micro(term: Term) -> bool:
        return term.sym == "text" and term.scale == 0

    def is_meso(term: Term) -> bool:
        return term.sym.startswith("F(text") or (term.sym.startswith("expand[text") and term.scale == 1)

    rules = [
        Rule(name="to-meso", pattern=Pattern(predicate=is_micro), action=expand_action(fanout=2)),
        Rule(name="to-macro", pattern=Pattern(predicate=is_meso), action=reduce_action(summarizer=_meso_summary)),
    ]

    return Program(name="text-pipeline", root=root, rules=rules, max_steps=32)


def run_pipeline(text: str) -> Term:
    from src.interpreter import Interpreter

    program = make_text_program(text)
    execution = Interpreter().run(program)
    return execution.materialize_root()


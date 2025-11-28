from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.rewrite import Pattern, Rule
from src.runtime import Event, Runtime
from src.terms import Term


@dataclass(frozen=True)
class Program:
    """Declarative description of a Nanocode program."""

    name: str
    root: Term
    rules: List[Rule]
    max_steps: int = 256


@dataclass
class Execution:
    program: Program
    root_id: str
    events: List[Event]
    snapshot: dict
    stats: dict


def _validate_term(term: Term) -> None:
    if term.scale < 0:
        raise ValueError(f"Term {term.sym} has negative scale {term.scale}")

    for child in term.children:
        _validate_term(child)


def _validate_pattern(pattern: Pattern) -> None:
    if pattern.scale is not None and pattern.scale < 0:
        raise ValueError(f"Pattern scale cannot be negative: {pattern.scale}")


def validate_program(program: Program) -> None:
    """Basic sanity checks to catch malformed programs before execution."""

    if program.max_steps <= 0:
        raise ValueError("Program max_steps must be positive")

    seen_rules: set[str] = set()
    for rule in program.rules:
        if rule.name in seen_rules:
            raise ValueError(f"Duplicate rule name: {rule.name}")
        seen_rules.add(rule.name)
        _validate_pattern(rule.pattern)

    _validate_term(program.root)


class Interpreter:
    """Thin orchestration layer around the runtime and scheduler."""

    def run(
        self,
        program: Program,
        until_idle: bool = True,
        *,
        walk_children: bool = False,
        strict_matching: bool = False,
    ) -> Execution:
        validate_program(program)

        runtime = Runtime(
            program.rules,
            walk_children=walk_children,
            strict_matching=strict_matching,
        )
        root_id = runtime.load(program.root)

        if until_idle:
            events = runtime.run_until_idle(max_steps=program.max_steps)
        else:
            events = runtime.run(max_steps=program.max_steps)

        return Execution(
            program=program,
            root_id=root_id,
            events=events,
            snapshot=runtime.snapshot(),
            stats=runtime.stats(),
        )


from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.rewrite import Rule
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


class Interpreter:
    """Thin orchestration layer around the runtime and scheduler."""

    def run(self, program: Program, until_idle: bool = True) -> Execution:
        runtime = Runtime(program.rules)
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
        )


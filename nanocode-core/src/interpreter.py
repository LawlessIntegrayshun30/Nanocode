from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.rewrite import Pattern, Rule, conflicting_rules
from src.runtime import Event, Runtime
from src.terms import Term


@dataclass(frozen=True)
class Program:
    """Declarative description of a Nanocode program."""

    name: str
    root: Term
    rules: List[Rule]
    max_steps: int = 256
    max_terms: Optional[int] = None

    def with_root(self, root: Term) -> "Program":
        """Return a copy of this program using a different root term."""

        return Program(
            name=self.name,
            root=root,
            rules=self.rules,
            max_steps=self.max_steps,
            max_terms=self.max_terms,
        )


@dataclass
class Execution:
    program: Program
    root_id: str
    events: List[Event]
    snapshot: dict
    stats: dict

    def materialize_store(self) -> "TermStore":
        """Rehydrate a ``TermStore`` from the captured runtime snapshot."""

        from src.term_store import TermStore

        records_payload = {
            term_id: {
                "sym": record.sym,
                "scale": record.scale,
                "children": list(record.children),
            }
            for term_id, record in self.snapshot["records"].items()
        }
        return TermStore.from_json({"records": records_payload})

    def final_term_id(self) -> str:
        """Return the last produced term ID (or the original root if no events)."""

        if self.events:
            return self.events[-1].after
        return self.root_id

    def materialize_root(self) -> Term:
        """Materialize the final root term from the captured snapshot."""

        store = self.materialize_store()
        return store.materialize(self.final_term_id())


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
    if program.max_terms is not None and program.max_terms <= 0:
        raise ValueError("Program max_terms must be positive when provided")

    seen_rules: set[str] = set()
    for rule in program.rules:
        if rule.name in seen_rules:
            raise ValueError(f"Duplicate rule name: {rule.name}")
        seen_rules.add(rule.name)
        _validate_pattern(rule.pattern)

    _validate_term(program.root)


def detect_conflicts(rules: List[Rule]) -> list[tuple[Rule, Rule]]:
    """Lightweight conflict detection for clearly overlapping patterns."""

    return conflicting_rules(rules)


class Interpreter:
    """Thin orchestration layer around the runtime and scheduler."""

    def run(
        self,
        program: Program,
        until_idle: bool = True,
        *,
        walk_children: bool = False,
        walk_depth: Optional[int] = None,
        strict_matching: bool = False,
        rule_budgets: Optional[Dict[str, int]] = None,
        max_terms: Optional[int] = None,
        include_rules: Optional[List[str]] = None,
        exclude_rules: Optional[List[str]] = None,
        include_scales: Optional[List[int]] = None,
        exclude_scales: Optional[List[int]] = None,
        detect_conflicts: bool = False,
    ) -> Execution:
        validate_program(program)

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

        if detect_conflicts:
            conflicts = conflicting_rules(program.rules)
            if conflicts:
                details = ", ".join(f"{a.name}/{b.name}" for a, b in conflicts)
                raise ValueError(f"Conflicting rule patterns detected: {details}")

        limit = max_terms if max_terms is not None else program.max_terms
        runtime = Runtime(
            program.rules,
            walk_children=walk_children,
            walk_depth=walk_depth,
            strict_matching=strict_matching,
            rule_budgets=rule_budgets,
            max_terms=limit,
            include_rules=include_rules,
            exclude_rules=exclude_rules,
            include_scales=include_scales,
            exclude_scales=exclude_scales,
            detect_conflicts=detect_conflicts,
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


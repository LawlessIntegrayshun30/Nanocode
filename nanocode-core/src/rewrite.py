from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from src.term_store import TermStore
from src.terms import Term, expand, reduce


@dataclass(frozen=True)
class Action:
    """Named, metadata-carrying rewrite action.

    Actions remain regular callables while exposing a stable `name` and
    structured `params` mapping so they can be serialized into Nanocode
    terms and round-tripped as meta-level data. This keeps rewrite
    semantics deterministic while making rule sets representable as data
    for evolution or self-hosted interpreters.
    """

    name: str
    params: dict[str, object]
    fn: Callable[[Term, TermStore], Term]

    def __call__(self, term: Term, store: TermStore) -> Term:  # pragma: no cover - thin wrapper
        return self.fn(term, store)


def expand_action(fanout: int = 3) -> Action:
    return Action(name="expand", params={"fanout": fanout}, fn=lambda term, store: expand(term, fanout=fanout))


def reduce_action(summarizer: Callable[[list[Term]], str] | None = None) -> Action:
    params = {"summarizer": summarizer.__name__} if summarizer else {}
    return Action(
        name="reduce",
        params=params,
        fn=lambda term, store: reduce(term, summarizer=summarizer),
    )


def lift_action() -> Action:
    """Raise a term to the next scale while preserving its subtree."""

    def _lift(term: Term, _store: TermStore) -> Term:
        return Term(sym=f"lift[{term.sym}]", scale=term.scale + 1, children=[term])

    return Action(name="lift", params={}, fn=_lift)


def action_from_spec(
    name: str,
    params: dict[str, object],
    summarizers: dict[str, Callable[[list[Term]], str]] | None = None,
) -> Action:
    if name == "expand":
        fanout = int(params.get("fanout", 3))
        return expand_action(fanout=fanout)
    if name == "reduce":
        summarizer_name = params.get("summarizer")
        if summarizer_name is None:
            return reduce_action()
        if summarizers and summarizer_name in summarizers:
            return reduce_action(summarizer=summarizers[summarizer_name])
        raise ValueError(f"Unknown summarizer '{summarizer_name}' for reduce action")
    if name == "lift":
        return lift_action()
    raise ValueError(f"Unknown action spec: {name}")


@dataclass(frozen=True)
class Pattern:
    sym: Optional[str] = None
    scale: Optional[int] = None
    predicate: Optional[Callable[[Term], bool]] = None

    def matches(self, term: Term) -> bool:
        if self.sym is not None and term.sym != self.sym:
            return False
        if self.scale is not None and term.scale != self.scale:
            return False
        if self.predicate and not self.predicate(term):
            return False
        return True


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: Pattern
    action: Callable[[Term, TermStore], Term]

    def applies(self, term: Term) -> bool:
        return self.pattern.matches(term)


class AmbiguousRuleError(Exception):
    def __init__(self, term: Term, rules: Iterable[Rule]):
        rule_names = ", ".join(rule.name for rule in rules)
        super().__init__(f"ambiguous match for term {term.sym} at scale {term.scale}: {rule_names}")
        self.term = term
        self.rules = list(rules)


def matching_rules(rules: list[Rule], term: Term) -> list[Rule]:
    return [rule for rule in rules if rule.applies(term)]


def first_match(rules: list[Rule], term: Term) -> Optional[Rule]:
    matches = matching_rules(rules, term)
    return matches[0] if matches else None


def conflicting_rules(rules: list[Rule]) -> list[tuple[Rule, Rule]]:
    """Identify rule pairs that deterministically overlap.

    Today we only flag conflicts when both rules target the same symbol and
    scale without predicates. Broader confluence checking is left for future
    work but this provides a lightweight guardrail against accidental
    ambiguity.
    """

    conflicts: list[tuple[Rule, Rule]] = []
    seen: dict[tuple[str, int], Rule] = {}
    for rule in rules:
        pattern = rule.pattern
        if pattern.predicate is not None:
            continue
        if pattern.sym is None or pattern.scale is None:
            continue

        key = (pattern.sym, pattern.scale)
        other = seen.get(key)
        if other is None:
            seen[key] = rule
            continue
        conflicts.append((other, rule))

    return conflicts

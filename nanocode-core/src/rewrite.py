from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from src.term_store import TermStore
from src.terms import Term


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

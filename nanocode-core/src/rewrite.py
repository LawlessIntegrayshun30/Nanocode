from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

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


def first_match(rules: list[Rule], term: Term) -> Optional[Rule]:
    for rule in rules:
        if rule.applies(term):
            return rule
    return None

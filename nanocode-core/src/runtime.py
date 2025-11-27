from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from src.rewrite import AmbiguousRuleError, Rule, matching_rules
from src.scheduler import FIFOScheduler
from src.term_store import TermStore
from src.terms import Term, term_to_dict


@dataclass
class Event:
    before: str
    after: str
    rule: str
    scale: int
    before_term: Term
    after_term: Term

    def as_dict(self) -> Dict[str, object]:  # pragma: no cover - convenience helper
        return {
            "before": self.before,
            "after": self.after,
            "rule": self.rule,
            "scale": self.scale,
            "before_term": self.before_term,
            "after_term": self.after_term,
        }

    def to_record(self) -> Dict[str, object]:
        """JSON-ready event representation for tracing."""

        return {
            "before": self.before,
            "after": self.after,
            "rule": self.rule,
            "scale": self.scale,
            "before_term": term_to_dict(self.before_term),
            "after_term": term_to_dict(self.after_term),
        }


class Runtime:
    """Minimal stepping runtime for Nanocode rewrites."""

    def __init__(
        self,
        rules: List[Rule],
        scheduler: Optional[FIFOScheduler] = None,
        event_hooks: Optional[List[Callable[[Event], None]]] = None,
        walk_children: bool = False,
        strict_matching: bool = False,
    ):
        self.store = TermStore()
        self.rules = rules
        self.scheduler = scheduler or FIFOScheduler()
        self.event_hooks: List[Callable[[Event], None]] = event_hooks or []
        self.events: List[Event] = []
        self.root_id: Optional[str] = None
        self._processed: set[str] = set()
        self._queued: set[str] = set()
        self.walk_children = walk_children
        self.strict_matching = strict_matching
        self.rule_counts: Dict[str, int] = {}
        self.scale_counts: Dict[int, int] = {}

    def load(self, root: Term) -> str:
        # Reset state for a fresh program load
        self.store = TermStore()
        self.events.clear()
        self._processed.clear()
        self._queued.clear()
        self.scheduler.clear()
        self.rule_counts.clear()
        self.scale_counts.clear()

        self.root_id = self.store.add_term(root)
        self._schedule_tree(self.root_id)
        return self.root_id

    def _schedule_term(self, term_id: str) -> None:
        if term_id in self._processed or term_id in self._queued:
            return

        self.scheduler.push(term_id)
        self._queued.add(term_id)

    def _schedule_tree(self, term_id: str) -> None:
        self._schedule_term(term_id)
        if not self.walk_children:
            return

        for child_id in self.store.children_of(term_id):
            self._schedule_tree(child_id)

    def step(self) -> Optional[Event]:
        term_id = self.scheduler.pop()
        if term_id is None:
            return None

        self._queued.discard(term_id)

        term = self.store.materialize(term_id)
        self._processed.add(term_id)
        matches = matching_rules(self.rules, term)
        if self.strict_matching and len(matches) > 1:
            raise AmbiguousRuleError(term, matches)

        rule = matches[0] if matches else None
        if rule is None:
            return None

        new_term = rule.action(term, self.store)
        new_id = self.store.add_term(new_term)
        event = Event(
            before=term_id,
            after=new_id,
            rule=rule.name,
            scale=term.scale,
            before_term=term,
            after_term=new_term,
        )
        self.events.append(event)
        self.rule_counts[rule.name] = self.rule_counts.get(rule.name, 0) + 1
        self.scale_counts[term.scale] = self.scale_counts.get(term.scale, 0) + 1
        for hook in self.event_hooks:
            hook(event)

        # Only push again if the term actually changed to avoid endless cycles when
        # a rule is idempotent with respect to the store's interning.
        if new_id != term_id and new_id not in self._processed:
            self._schedule_tree(new_id)
        return event

    def run(self, max_steps: int = 1) -> List[Event]:
        emitted: List[Event] = []
        for _ in range(max_steps):
            ev = self.step()
            if ev is None:
                if len(self.scheduler) == 0:
                    break
                continue
            emitted.append(ev)
        return emitted

    def run_until_idle(self, max_steps: Optional[int] = None) -> List[Event]:
        """Drive the scheduler until it empties or a step budget is hit."""

        emitted: List[Event] = []
        steps = 0
        while len(self.scheduler):
            ev = self.step()
            if ev is not None:
                emitted.append(ev)

            steps += 1
            if max_steps is not None and steps >= max_steps:
                break

        return emitted

    def snapshot(self) -> Dict[str, object]:
        return {
            "root": self.root_id,
            "events": list(self.events),
            "records": self.store.snapshot(),
            "frontier": self.scheduler.pending(),
            "rule_counts": dict(self.rule_counts),
            "scale_counts": dict(self.scale_counts),
        }

    def stats(self) -> Dict[str, object]:
        """Summaries of runtime activity and remaining work."""

        return {
            "events": len(self.events),
            "rule_counts": dict(self.rule_counts),
            "scale_counts": dict(self.scale_counts),
            "frontier": list(self.scheduler.pending()),
            "store_size": len(self.store),
        }

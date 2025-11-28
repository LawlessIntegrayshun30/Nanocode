from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from src.rewrite import AmbiguousRuleError, Rule, matching_rules
from src.scheduler import FIFOScheduler, LIFOScheduler, RandomScheduler
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
        scheduler: Optional[FIFOScheduler | LIFOScheduler | RandomScheduler] = None,
        event_hooks: Optional[List[Callable[[Event], None]]] = None,
        walk_children: bool = False,
        strict_matching: bool = False,
        rule_budgets: Optional[Dict[str, int]] = None,
        max_terms: Optional[int] = None,
    ):
        if max_terms is not None and max_terms <= 0:
            raise ValueError("max_terms must be positive when provided")

        self.store = TermStore()
        self.rules = rules
        self.scheduler = scheduler if scheduler is not None else FIFOScheduler()
        self.event_hooks: List[Callable[[Event], None]] = event_hooks or []
        self.events: List[Event] = []
        self.root_id: Optional[str] = None
        self._processed: set[str] = set()
        self._queued: set[str] = set()
        self.walk_children = walk_children
        self.strict_matching = strict_matching
        self.rule_counts: Dict[str, int] = {}
        self.scale_counts: Dict[int, int] = {}
        self.exhausted_budget: bool = False
        self.rule_budgets: Dict[str, int] = dict(rule_budgets) if rule_budgets else {}
        self.rule_budget_exhausted: set[str] = set()
        self.max_terms = max_terms
        self.term_limit_exhausted = False

    def _reset_state(self) -> None:
        self.events.clear()
        self._processed.clear()
        self._queued.clear()
        self.scheduler.clear()
        self.rule_counts.clear()
        self.scale_counts.clear()
        self.exhausted_budget = False
        self.rule_budget_exhausted.clear()
        self.term_limit_exhausted = False

    def load(self, root: Term) -> str:
        # Reset state for a fresh program load
        self.store = TermStore()
        self._reset_state()

        self.root_id = self.store.add_term(root)
        self._check_term_limit()
        self._schedule_tree(self.root_id)
        return self.root_id

    def load_state(
        self,
        *,
        store: TermStore,
        root_id: str,
        frontier: Optional[List[str]] = None,
        processed: Optional[List[str]] = None,
        rule_budgets: Optional[Dict[str, int]] = None,
        rule_budget_exhausted: Optional[List[str]] = None,
        scheduler_state: object | None = None,
    ) -> str:
        """Restore runtime state from a serialized snapshot."""

        def _coerce_state(payload: object | None) -> object | None:
            if isinstance(payload, list):
                return tuple(_coerce_state(item) for item in payload)
            if isinstance(payload, tuple):
                return tuple(_coerce_state(item) for item in payload)
            return payload

        self.store = store
        self._reset_state()

        if rule_budgets is not None:
            self.rule_budgets = dict(rule_budgets)
        if rule_budget_exhausted is not None:
            self.rule_budget_exhausted = set(rule_budget_exhausted)

        if root_id not in self.store:
            raise KeyError(f"Root term {root_id} not found in store")

        self.root_id = root_id
        if processed:
            self._processed = set(processed)

        if frontier:
            for term_id in frontier:
                if term_id not in self.store:
                    raise KeyError(f"Frontier term {term_id} not found in store")
                self._schedule_term(term_id)
        else:
            self._schedule_tree(self.root_id)

        if scheduler_state is not None and hasattr(self.scheduler, "set_state"):
            self.scheduler.set_state(_coerce_state(scheduler_state))

        self._check_term_limit()
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

        limit = self.rule_budgets.get(rule.name)
        fired = self.rule_counts.get(rule.name, 0)
        if limit is not None and fired >= limit:
            self.rule_budget_exhausted.add(rule.name)
            return None

        new_term = rule.action(term, self.store)
        new_id = self.store.add_term(new_term)
        self._check_term_limit()
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
        if (
            not self.term_limit_exhausted
            and new_id != term_id
            and new_id not in self._processed
        ):
            self._schedule_tree(new_id)
        return event

    def run(self, max_steps: int = 1) -> List[Event]:
        emitted: List[Event] = []
        steps = 0
        for _ in range(max_steps):
            if self.term_limit_exhausted:
                break
            ev = self.step()
            steps += 1
            if ev is None:
                if len(self.scheduler) == 0:
                    break
                continue
            emitted.append(ev)

        self.exhausted_budget = steps >= max_steps and len(self.scheduler) > 0
        return emitted

    def run_until_idle(self, max_steps: Optional[int] = None) -> List[Event]:
        """Drive the scheduler until it empties or a step budget is hit."""

        emitted: List[Event] = []
        steps = 0
        while len(self.scheduler) and not self.term_limit_exhausted:
            ev = self.step()
            if ev is not None:
                emitted.append(ev)

            steps += 1
            if max_steps is not None and steps >= max_steps:
                self.exhausted_budget = len(self.scheduler) > 0
                break

        if max_steps is None or steps < max_steps:
            self.exhausted_budget = False

        return emitted

    def snapshot(self) -> Dict[str, object]:
        return {
            "root": self.root_id,
            "events": list(self.events),
            "records": self.store.snapshot(),
            "frontier": self.scheduler.pending(),
            "processed": set(self._processed),
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
            "idle": len(self.scheduler) == 0,
            "budget_exhausted": self.exhausted_budget,
            "rule_budget_exhausted": sorted(self.rule_budget_exhausted),
            "term_limit_exhausted": self.term_limit_exhausted,
        }

    def state(self) -> Dict[str, object]:
        """Serializable snapshot of runtime data for persistence or replay."""

        return {
            "root": self.root_id,
            "records": self.store.to_json(),
            "frontier": list(self.scheduler.pending()),
            "processed": list(self._processed),
            "scheduler": self._scheduler_name(),
            "scheduler_seed": getattr(self.scheduler, "seed", None),
            "scheduler_state": self.scheduler.state() if hasattr(self.scheduler, "state") else None,
            "walk_children": self.walk_children,
            "strict_matching": self.strict_matching,
            "rule_budgets": dict(self.rule_budgets),
            "rule_budget_exhausted": sorted(self.rule_budget_exhausted),
            "max_terms": self.max_terms,
            "term_limit_exhausted": self.term_limit_exhausted,
        }

    def _scheduler_name(self) -> str:
        if isinstance(self.scheduler, LIFOScheduler):
            return "lifo"
        if isinstance(self.scheduler, RandomScheduler):
            return "random"
        return "fifo"

    def _check_term_limit(self) -> None:
        if self.max_terms is None:
            return

        if len(self.store) > self.max_terms:
            self.term_limit_exhausted = True

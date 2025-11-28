from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Tuple

from src.terms import Term


@dataclass(frozen=True)
class TermRecord:
    """Immutable representation of a term inside the store.

    Children are stored as IDs to enable structural sharing and deterministic hashing.
    """

    sym: str
    scale: int
    children: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TermKey:
    """Hashable key for interning a term in the store."""

    sym: str
    scale: int
    children: Tuple[str, ...]


class TermStore:
    """Persistent term store with structural sharing.

    Terms are interned by (sym, scale, child_ids) and addressed by stable IDs derived
    from their content. The store never mutates existing records, enabling snapshots
    and deterministic replay of rewrite steps.
    """

    def __init__(self) -> None:
        self._records: Dict[str, TermRecord] = {}
        self._index: Dict[TermKey, str] = {}

    def add_term(self, term: Term) -> str:
        """Add a term (recursively) and return its stable ID.

        If an equivalent term already exists, the existing ID is returned.
        """

        child_ids = tuple(self.add_term(child) for child in term.children)
        key = TermKey(term.sym, term.scale, child_ids)
        if key in self._index:
            return self._index[key]

        term_id = self._hash_key(key)
        self._records[term_id] = TermRecord(term.sym, term.scale, child_ids)
        self._index[key] = term_id
        return term_id

    def get(self, term_id: str) -> TermRecord:
        return self._records[term_id]

    def materialize(self, term_id: str) -> Term:
        """Reconstruct a `Term` tree from a stored ID."""

        record = self.get(term_id)
        children = [self.materialize(cid) for cid in record.children]
        return Term(sym=record.sym, scale=record.scale, children=children)

    def children_of(self, term_id: str) -> Tuple[str, ...]:
        """Return the immediate child IDs for a stored term."""

        return self.get(term_id).children

    def snapshot(self) -> Dict[str, TermRecord]:
        """Return a shallow copy of stored records for inspection/replay."""

        return dict(self._records)

    def to_json(self) -> Dict[str, Dict[str, object]]:
        """JSON-friendly view of stored records keyed by term ID."""

        return {
            term_id: {"sym": record.sym, "scale": record.scale, "children": list(record.children)}
            for term_id, record in self._records.items()
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Mapping[str, object]]) -> "TermStore":
        """Rehydrate a term store from a JSON-ready mapping."""

        store = cls()
        records = payload["records"] if "records" in payload else payload
        for term_id, record_data in records.items():
            children = tuple(str(child) for child in record_data.get("children", ()))
            record = TermRecord(
                sym=str(record_data["sym"]),
                scale=int(record_data["scale"]),
                children=children,
            )
            store._records[term_id] = record
            store._index[TermKey(record.sym, record.scale, record.children)] = term_id
        return store

    def to_bundle(
        self,
        *,
        root: str | None = None,
        frontier: Iterable[str] | None = None,
        scheduler: str | None = None,
        scheduler_seed: int | None = None,
        scheduler_state: object | None = None,
        processed: Iterable[str] | None = None,
        walk_children: bool | None = None,
        strict_matching: bool | None = None,
        walk_depth: int | None = None,
        rule_budgets: Dict[str, int] | None = None,
        rule_budget_exhausted: Iterable[str] | None = None,
        max_terms: int | None = None,
        term_limit_exhausted: bool | None = None,
        include_rules: Iterable[str] | None = None,
        exclude_rules: Iterable[str] | None = None,
        include_scales: Iterable[int] | None = None,
        exclude_scales: Iterable[int] | None = None,
        detect_conflicts: bool | None = None,
    ) -> Dict[str, object]:
        """Package the store with runtime metadata for replay/resume."""

        bundle: Dict[str, object] = {
            "records": self.to_json(),
        }

        if root is not None:
            bundle["root"] = root
        if frontier is not None:
            bundle["frontier"] = list(frontier)
        if scheduler is not None:
            bundle["scheduler"] = scheduler
        if scheduler_seed is not None:
            bundle["scheduler_seed"] = scheduler_seed
        if scheduler_state is not None:
            bundle["scheduler_state"] = scheduler_state
        if processed is not None:
            bundle["processed"] = list(processed)
        if walk_children is not None:
            bundle["walk_children"] = walk_children
        if strict_matching is not None:
            bundle["strict_matching"] = strict_matching
        if walk_depth is not None:
            bundle["walk_depth"] = walk_depth
        if rule_budgets is not None:
            bundle["rule_budgets"] = dict(rule_budgets)
        if rule_budget_exhausted is not None:
            bundle["rule_budget_exhausted"] = list(rule_budget_exhausted)
        if max_terms is not None:
            bundle["max_terms"] = max_terms
        if term_limit_exhausted is not None:
            bundle["term_limit_exhausted"] = term_limit_exhausted
        if include_rules is not None:
            bundle["include_rules"] = list(include_rules)
        if exclude_rules is not None:
            bundle["exclude_rules"] = list(exclude_rules)
        if include_scales is not None:
            bundle["include_scales"] = list(include_scales)
        if exclude_scales is not None:
            bundle["exclude_scales"] = list(exclude_scales)
        if detect_conflicts is not None:
            bundle["detect_conflicts"] = detect_conflicts

        return bundle

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._records)

    @staticmethod
    def _hash_key(key: TermKey) -> str:
        raw = f"{key.sym}|{key.scale}|{','.join(key.children)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def __contains__(self, term_id: str) -> bool:  # pragma: no cover - trivial
        return term_id in self._records

    def iter_records(self) -> Iterable[Tuple[str, TermRecord]]:
        return self._records.items()

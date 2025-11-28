from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

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

    def snapshot(self) -> Dict[str, TermRecord]:
        """Return a shallow copy of stored records for inspection/replay."""

        return dict(self._records)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._records)

    @staticmethod
    def _hash_key(key: TermKey) -> str:
        raw = f"{key.sym}|{key.scale}|{','.join(key.children)}"
        # Use the full SHA-256 hex digest to minimize collision risk.
        return hashlib.sha256(raw.encode()).hexdigest()

    def __contains__(self, term_id: str) -> bool:  # pragma: no cover - trivial
        return term_id in self._records

    def iter_records(self) -> Iterable[Tuple[str, TermRecord]]:
        return self._records.items()

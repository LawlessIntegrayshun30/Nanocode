from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.terms import Term


class SignatureError(ValueError):
    """Raised when a term violates a declared Nanocode signature."""


@dataclass(frozen=True)
class TermSignature:
    sym: str
    min_children: int = 0
    max_children: int | None = None
    allowed_scales: set[int] | None = None

    def validate(self, term: Term) -> None:
        if term.sym != self.sym:
            raise SignatureError(f"signature mismatch: expected {self.sym}, got {term.sym}")
        if term.scale < 0:
            raise SignatureError(f"term {term.sym} has negative scale {term.scale}")
        if term.children is None:
            raise SignatureError(f"term {term.sym} must expose children list")

        count = len(term.children)
        if count < self.min_children:
            raise SignatureError(
                f"term {term.sym} expected at least {self.min_children} children, found {count}"
            )
        if self.max_children is not None and count > self.max_children:
            raise SignatureError(
                f"term {term.sym} expected at most {self.max_children} children, found {count}"
            )
        if self.allowed_scales is not None and term.scale not in self.allowed_scales:
            raise SignatureError(
                f"term {term.sym} scale {term.scale} not in allowed scales {sorted(self.allowed_scales)}"
            )


class Signature:
    """Declarative term constraints for Nanocode genomes."""

    def __init__(self, entries: Iterable[TermSignature]):
        entries_list = list(entries)
        self._by_sym = {entry.sym: entry for entry in entries_list}
        if len(self._by_sym) != len(entries_list):
            raise SignatureError("duplicate signature entries detected")

    def get(self, sym: str) -> TermSignature | None:
        return self._by_sym.get(sym)

    def items(self) -> list[tuple[str, TermSignature]]:
        """Deterministic access to signature entries."""

        return sorted(self._by_sym.items())

    def validate_term(self, term: Term) -> None:
        entry = self.get(term.sym)
        if entry is None:
            raise SignatureError(f"no signature declared for symbol {term.sym}")
        entry.validate(term)

    def validate_tree(self, term: Term) -> None:
        self.validate_term(term)
        for child in term.children:
            self.validate_tree(child)

    def to_dict(self) -> dict:
        return {
            "symbols": {
                sym: {
                    "min_children": entry.min_children,
                    "max_children": entry.max_children,
                    "scales": sorted(entry.allowed_scales) if entry.allowed_scales is not None else None,
                }
                for sym, entry in sorted(self._by_sym.items())
            }
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Signature":
        try:
            symbols = payload["symbols"]
        except KeyError as exc:  # pragma: no cover - defensive
            raise SignatureError("signature payload missing 'symbols'") from exc

        entries: list[TermSignature] = []
        for sym, spec in symbols.items():
            entries.append(
                TermSignature(
                    sym=sym,
                    min_children=int(spec.get("min_children", 0)),
                    max_children=(
                        int(spec["max_children"]) if spec.get("max_children") is not None else None
                    ),
                    allowed_scales=set(spec["scales"]) if spec.get("scales") is not None else None,
                )
            )
        return cls(entries)


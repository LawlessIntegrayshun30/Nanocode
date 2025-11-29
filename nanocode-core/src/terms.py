from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List

@dataclass(frozen=True)
class Term:
    sym: str
    scale: int = 0
    children: List["Term"] = field(default_factory=list)

def expand(t: Term, fanout: int = 3) -> Term:
    """Construct a higher-scale motif from lower-scale structure.

    Instead of merely renaming a symbol, expansion lifts the existing
    structure by emitting explicit motif children derived from the
    lower-scale leaves. Each motif captures contiguous slices of the
    leaf sequence up to ``fanout`` tokens, turning scale into a structural
    coordinate rather than a label.
    """

    def _leaves(term: Term) -> List[Term]:
        stack = [term]
        leaves: List[Term] = []
        while stack:
            node = stack.pop()
            if not node.children:
                leaves.append(node)
                continue
            stack.extend(reversed(node.children))
        return leaves

    leaves = _leaves(t)
    if not leaves:
        leaves = [t]

    motifs: List[Term] = []
    for size in range(1, min(fanout, len(leaves)) + 1):
        for idx in range(0, len(leaves) - size + 1):
            window = leaves[idx : idx + size]
            label = "|".join(child.sym for child in window)
            motifs.append(
                Term(
                    sym=f"motif[{label}]",
                    scale=t.scale + 1,
                    children=list(window),
                )
            )

    if not motifs and fanout > 0:
        # If we have fewer leaves than the requested fanout, synthesize
        # repeated motifs to preserve the requested branching factor.
        motifs = [
            Term(sym=f"motif[{t.sym}#{i}]", scale=t.scale + 1, children=[leaves[0]])
            for i in range(fanout)
        ]

    while len(motifs) < fanout:
        motifs.append(
            Term(
                sym=f"motif[{t.sym}#{len(motifs)}]",
                scale=t.scale + 1,
                children=[leaves[0]],
            )
        )

    return Term(
        sym=f"F({t.sym})",
        scale=t.scale + 1,
        children=motifs,
    )

def reduce(u: Term, summarizer: Callable[[List[Term]], str] | None = None) -> Term:
    """Collapse a higher-scale motif back to a lower-scale representative.

    The summarizer's output is threaded into the reduced term to preserve
    provenance. By default we emit a stable summary derived from child
    symbols and scales so round-tripping through expand→reduce produces a
    structure that reflects the lower-scale evidence.
    """

    if not u.children:
        return u

    base_sym = u.sym
    if u.sym.startswith("expand[") and u.sym.endswith("]"):
        base_sym = u.sym[len("expand[") : -1]
    if u.sym.startswith("F(") and u.sym.endswith(")"):
        base_sym = u.sym[2:-1]

    if summarizer is None:
        summarizer = _default_summarizer

    summary = summarizer(u.children)
    summary_child = Term(sym=f"summary:{summary}", scale=u.scale - 1)
    return Term(sym=base_sym, scale=u.scale - 1, children=[summary_child])


def _default_summarizer(children: Iterable[Term]) -> str:
    counts: Dict[str, int] = {}

    def _walk(term: Term) -> None:
        key = f"{term.sym}@{term.scale}"
        counts[key] = counts.get(key, 0) + 1
        for child in term.children:
            _walk(child)

    for child in children:
        _walk(child)

    parts = [f"{key}={counts[key]}" for key in sorted(counts)]
    return ";".join(parts)


def term_to_dict(term: Term) -> Dict[str, Any]:
    """Serialize a term into a JSON-friendly dict for tracing."""

    return {
        "sym": term.sym,
        "scale": term.scale,
        "children": [term_to_dict(child) for child in term.children],
    }

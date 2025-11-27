from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Callable

@dataclass(frozen=True)
class Term:
    sym: str
    scale: int = 0
    children: List["Term"] = field(default_factory=list)

def expand(t: Term, fanout: int = 3) -> Term:
    new_scale = t.scale + 1
    children = [
        Term(sym=f"{t.sym}.{i}", scale=new_scale)
        for i in range(fanout)
    ]
    return Term(sym=f"F({t.sym})", scale=new_scale, children=children)

def reduce(u: Term, summarizer: Callable[[List[Term]], str] = None) -> Term:
    if not (u.sym.startswith("F(") and u.sym.endswith(")")):
        return u

    base_sym = u.sym[2:-1]

    if summarizer:
        _ = summarizer(u.children)

    return Term(sym=base_sym, scale=u.scale - 1)

import random

from src.terms import Term, expand, reduce


def test_expand_reduce_identity():
    t = Term("A", 0)
    round_trip = reduce(expand(t))
    assert round_trip.sym == "A"
    assert round_trip.scale == 0
    assert round_trip.children[0].sym.startswith("summary:")


def _random_term(depth: int, scale: int = 0) -> Term:
    sym = random.choice(["a", "b", "c", "x", "y"])
    if depth <= 1:
        return Term(sym=sym, scale=scale)
    fanout = random.randint(1, 3)
    children = [_random_term(depth - 1, scale=scale) for _ in range(fanout)]
    return Term(sym=sym, scale=scale, children=children)


def test_expand_reduce_preserves_base_symbol_and_summarizes_children():
    random.seed(42)
    for _ in range(10):
        base = _random_term(depth=3)
        expanded = expand(base, fanout=3)
        reduced = reduce(expanded)
        assert reduced.sym == base.sym
        assert reduced.scale == base.scale
        summary = reduced.children[0].sym
        def _flatten(term):
            if not term.children:
                yield term.sym
            for child in term.children:
                yield from _flatten(child)

        for leaf_sym in _flatten(base):
            assert leaf_sym in summary


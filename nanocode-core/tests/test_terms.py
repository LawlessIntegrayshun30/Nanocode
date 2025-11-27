from src.terms import Term, expand, reduce

def test_expand_reduce_identity():
    t = Term("A", 0)
    assert reduce(expand(t)).sym == "A"
    assert reduce(expand(t)).scale == 0

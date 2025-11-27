from src.term_store import TermStore
from src.terms import Term


def test_term_store_deduplicates_structurally_equal_terms():
    store = TermStore()
    t1 = Term("A", 0, [Term("B", 1), Term("C", 1)])
    t2 = Term("A", 0, [Term("B", 1), Term("C", 1)])

    id1 = store.add_term(t1)
    id2 = store.add_term(t2)

    assert id1 == id2
    assert len(store.snapshot()) == 3  # A, B, C


def test_term_materialization_round_trip():
    store = TermStore()
    root = Term("root", 0, [Term("leaf", 1)])
    root_id = store.add_term(root)

    rebuilt = store.materialize(root_id)
    assert rebuilt == root

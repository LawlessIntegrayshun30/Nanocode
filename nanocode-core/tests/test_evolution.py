from random import Random

from src.evolution import (
    Genome,
    crossover_terms,
    delete_subtree,
    insert_subtree,
    mutate_scale,
    mutate_symbol,
)
from src.terms import Term


def test_mutate_symbol_uses_pool_and_rng():
    term = Term("root", children=[Term("a"), Term("b")])
    rng = Random(0)

    mutated = mutate_symbol(term, ["a", "b", "c"], rng=rng)

    assert mutated.children[0].sym == "c"
    assert mutated.children[1] == term.children[1]


def test_mutate_scale_respects_bounds():
    term = Term("root", scale=1, children=[Term("a", scale=2), Term("b", scale=3)])
    rng = Random(1)

    mutated = mutate_scale(term, delta_range=(-2, 2), min_scale=0, max_scale=3, rng=rng)

    assert mutated.scale == 3
    assert mutated.children[0].scale == 2


def test_delete_subtree_skips_root():
    term = Term("root", children=[Term("a", children=[Term("a1")]), Term("b")])
    rng = Random(0)

    mutated = delete_subtree(term, rng=rng)

    assert mutated.children == [Term("a"), Term("b")]


def test_insert_subtree_appends_spawned_child():
    term = Term("root", children=[Term("a")])
    rng = Random(0)

    def spawn(parent: Term) -> Term:
        return Term(sym=f"{parent.sym}.child", scale=parent.scale + 1)

    mutated = insert_subtree(term, spawn, rng=rng)

    assert mutated.children[0].children == [Term("a.child", scale=1)]


def test_crossover_swaps_subtrees_deterministically():
    a = Term("A", children=[Term("a1"), Term("a2")])
    b = Term("B", children=[Term("b1"), Term("b2")])
    rng = Random(1)

    new_a, new_b = crossover_terms(a, b, rng=rng)

    assert new_a == Term("b2")
    assert new_b.children[1] == Term("A", children=[Term("a1"), Term("a2")])


def test_genome_annotations_allow_metadata():
    genome = Genome(root=Term("root"), annotations={"score": 0.5})

    assert genome.annotations == {"score": 0.5}

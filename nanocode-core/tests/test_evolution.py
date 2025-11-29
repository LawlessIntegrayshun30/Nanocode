from random import Random

from src.evolution import (
    EvolutionConfig,
    Evaluation,
    Genome,
    annotate_genome,
    crossover_terms,
    delete_subtree,
    evaluate_population,
    evolve_population,
    genome_from_dict,
    genome_to_dict,
    insert_subtree,
    load_population,
    mutate_scale,
    mutate_symbol,
    snapshot_population,
)
from src.constraints import StructuralConstraints
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


def test_evaluate_population_returns_sorted_scores_with_info():
    genomes = [Genome(root=Term("a")), Genome(root=Term("b"))]

    def scorer(genome: Genome) -> tuple[float, dict]:
        return (1.0 if genome.root.sym == "a" else 0.25, {"sym": genome.root.sym})

    evaluations = evaluate_population(genomes, scorer)

    assert [ev.genome.root.sym for ev in evaluations] == ["a", "b"]
    assert evaluations[0].info == {"sym": "a"}


def test_annotate_genome_merges_metadata():
    genome = Genome(root=Term("root"), annotations={"score": 1})

    annotated = annotate_genome(genome, parent=0, score=2)

    assert annotated.annotations == {"score": 2, "parent": 0}


def test_evolve_population_runs_deterministically():
    genomes = [Genome(root=Term("bar")) for _ in range(3)]
    rng = Random(0)
    config = EvolutionConfig(
        population_size=3,
        generations=2,
        mutation_rate=1.0,
        crossover_rate=0.0,
        elitism=1,
        tournament_size=2,
    )

    def scorer(genome: Genome) -> float:
        return 1.0 if genome.root.sym == "foo" else 0.0

    def mutate(genome: Genome, rng: Random) -> Genome:
        mutated = mutate_symbol(genome.root, ["foo", "bar"], rng=rng)
        return Genome(root=mutated, annotations=genome.annotations)

    seen_best: list[Evaluation] = []

    def on_generation(generation: int, best: Evaluation, _: list[Evaluation]):
        seen_best.append(best)

    final = evolve_population(
        genomes,
        scorer,
        mutate,
        config=config,
        rng=rng,
        on_generation=on_generation,
    )

    assert len(seen_best) == config.generations
    assert final[0].score == 1.0
    assert final[0].genome.root.sym == "foo"


def test_snapshot_population_round_trips_with_fingerprints():
    genomes = [
        Genome(root=Term("root", children=[Term("a")])),
        Genome(root=Term("root", children=[Term("b")]), annotations={"score": 1}),
    ]

    snapshot = snapshot_population(genomes)
    restored = load_population(snapshot)

    assert [g.root for g in restored] == [g.root for g in genomes]
    assert [g.annotations for g in restored] == [g.annotations for g in genomes]
    assert [g.fingerprint for g in restored] == [g.fingerprint for g in genomes]


def test_load_population_rejects_fingerprint_mismatch():
    genome = Genome(root=Term("root"))
    payload = genome_to_dict(genome)
    payload["fingerprint"] = "mismatch"

    snapshot = {"genomes": [payload]}

    try:
        load_population(snapshot)
    except ValueError as exc:
        assert "fingerprint mismatch" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected fingerprint mismatch to raise")


def test_snapshot_population_enforces_constraints():
    genomes = [Genome(root=Term("root", children=[Term("child")]))]
    constraints = StructuralConstraints(max_depth=1)

    try:
        snapshot_population(genomes, constraints=constraints)
    except ValueError as exc:
        assert "max_depth" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected constraints violation")

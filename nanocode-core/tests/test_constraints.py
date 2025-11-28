from src.constraints import StructuralConstraints, measure_structure, validate_structure
from src.evolution import EvolutionConfig, Genome, evaluate_population, evolve_population
from src.terms import Term


def _sample_term() -> Term:
    return Term(
        sym="root",
        children=[
            Term(sym="leaf"),
            Term(sym="branch", scale=2, children=[Term(sym="child", scale=3)]),
        ],
    )


def test_measure_structure_tracks_size_depth_and_scales():
    metrics = measure_structure(_sample_term())

    assert metrics.nodes == 4
    assert metrics.leaves == 2
    assert metrics.max_depth == 3
    assert metrics.max_fanout == 2
    assert metrics.min_scale == 0
    assert metrics.max_scale == 3


def test_validate_structure_reports_violations():
    constraints = StructuralConstraints(
        max_nodes=2, max_depth=2, max_fanout=1, min_scale=1, max_scale=2
    )

    violations = validate_structure(_sample_term(), constraints)

    assert "nodes=4" in violations[0]
    assert any("max_depth=3" in violation for violation in violations)
    assert any("max_fanout=2" in violation for violation in violations)
    assert any("min_scale=0" in violation for violation in violations)
    assert any("max_scale=3" in violation for violation in violations)


def test_evaluate_population_penalizes_constraint_violations():
    good = Genome(root=Term(sym="ok"))
    bad = Genome(root=_sample_term())

    evaluations = evaluate_population(
        [bad, good],
        scorer=lambda genome: (1.0, {"id": genome.root.sym}),
        constraints=StructuralConstraints(max_nodes=1),
        violation_penalty=-99,
    )

    assert evaluations[0].genome is good
    assert evaluations[0].score == 1.0
    assert evaluations[1].score == -99
    assert "violations" in evaluations[1].info


def test_evolve_population_propagates_constraints_and_penalties():
    bad = Genome(root=_sample_term())

    config = EvolutionConfig(
        population_size=1,
        generations=1,
        mutation_rate=0.0,
        crossover_rate=0.0,
        elitism=0,
        tournament_size=1,
        constraints=StructuralConstraints(max_nodes=1),
        violation_penalty=-50,
    )

    final = evolve_population(
        [bad],
        scorer=lambda genome: 1.0,
        mutate=lambda genome, rng: genome,
        config=config,
        rng=None,
    )

    assert final[0].score == -50
    assert "violations" in final[0].info

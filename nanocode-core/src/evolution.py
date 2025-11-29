from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence, Tuple

from src.constraints import StructuralConstraints, validate_structure
from src.terms import Term


@dataclass(frozen=True)
class Genome:
    """A Nanocode genome represented as a root term and optional rule payloads.

    The root term encodes the structure to evolve (e.g., an agent policy tree),
    while optional annotations can track provenance or scoring metadata without
    affecting rewrite semantics.
    """

    root: Term
    annotations: dict | None = None


@dataclass(frozen=True)
class Evaluation:
    """An evaluated genome with an explicit fitness score and metadata."""

    genome: Genome
    score: float
    info: dict | None = None


@dataclass(frozen=True)
class EvolutionConfig:
    """Configuration for a deterministic evolutionary loop over Nanocode genomes."""

    population_size: int
    generations: int = 1
    mutation_rate: float = 0.5
    crossover_rate: float = 0.5
    elitism: int = 1
    tournament_size: int = 2
    constraints: StructuralConstraints | None = None
    violation_penalty: float = float("-inf")


def _iter_paths(term: Term, prefix: Tuple[int, ...] | Tuple[int] = ()) -> Iterable[Tuple[Tuple[int, ...], Term]]:
    yield prefix, term
    for idx, child in enumerate(term.children):
        yield from _iter_paths(child, prefix + (idx,))


def _replace_subterm(term: Term, path: Sequence[int], new_subterm: Term) -> Term:
    if not path:
        return new_subterm

    head, *rest = path
    children: List[Term] = list(term.children)
    children[head] = _replace_subterm(children[head], rest, new_subterm)
    return Term(sym=term.sym, scale=term.scale, children=children)


def mutate_symbol(term: Term, symbol_pool: Sequence[str], *, rng: random.Random | None = None) -> Term:
    """Replace the symbol of a randomly selected node with another from the pool.

    The mutation is deterministic with respect to the provided ``rng`` and
    leaves scales/children untouched.
    """

    rng = rng or random.Random()
    paths = list(_iter_paths(term))
    if not paths:
        return term

    path, node = rng.choice(paths)
    candidates = [sym for sym in symbol_pool if sym != node.sym] or [node.sym]
    new_sym = rng.choice(candidates)
    new_node = Term(sym=new_sym, scale=node.scale, children=node.children)
    return _replace_subterm(term, path, new_node)


def mutate_scale(
    term: Term,
    *,
    delta_range: Tuple[int, int] = (-1, 1),
    min_scale: int = 0,
    max_scale: int | None = None,
    rng: random.Random | None = None,
) -> Term:
    """Tweak the scale of a random node by a bounded delta.

    The adjusted scale is clamped to ``[min_scale, max_scale]`` when
    ``max_scale`` is provided.
    """

    rng = rng or random.Random()
    paths = list(_iter_paths(term))
    if not paths:
        return term

    path, node = rng.choice(paths)
    delta = rng.randint(delta_range[0], delta_range[1])
    new_scale = node.scale + delta
    if max_scale is not None:
        new_scale = min(new_scale, max_scale)
    new_scale = max(min_scale, new_scale)

    new_node = Term(sym=node.sym, scale=new_scale, children=node.children)
    return _replace_subterm(term, path, new_node)


def delete_subtree(term: Term, *, rng: random.Random | None = None) -> Term:
    """Remove a random non-root subtree.

    If the term is a leaf (no deletable children), it is returned unchanged.
    """

    rng = rng or random.Random()
    candidates = [(path, node) for path, node in _iter_paths(term) if path]
    if not candidates:
        return term

    path, _ = rng.choice(candidates)
    parent_path, delete_idx = path[:-1], path[-1]

    def _delete(node: Term, remaining: Sequence[int]) -> Term:
        if not remaining:
            return node
        head, *rest = remaining
        children: List[Term] = list(node.children)
        if not rest:
            del children[head]
        else:
            children[head] = _delete(children[head], rest)
        return Term(sym=node.sym, scale=node.scale, children=children)

    return _delete(term, parent_path + (delete_idx,))


def insert_subtree(
    term: Term,
    spawn: Callable[[Term], Term],
    *,
    rng: random.Random | None = None,
) -> Term:
    """Insert a spawned subtree as a new child of a random node.

    The ``spawn`` callable receives the chosen parent term, enabling context-
    aware generation (e.g., matching scale or symbol schemas).
    """

    rng = rng or random.Random()
    paths = list(_iter_paths(term))
    if not paths:
        return term

    path, parent = rng.choice(paths)
    new_child = spawn(parent)
    children: List[Term] = list(parent.children) + [new_child]
    new_parent = Term(sym=parent.sym, scale=parent.scale, children=children)
    return _replace_subterm(term, path, new_parent)


def crossover_terms(a: Term, b: Term, *, rng: random.Random | None = None) -> Tuple[Term, Term]:
    """Swap random subtrees between two genomes.

    The operation is deterministic with respect to ``rng`` and returns new
    roots, leaving the inputs unchanged.
    """

    rng = rng or random.Random()
    paths_a = list(_iter_paths(a))
    paths_b = list(_iter_paths(b))
    path_a, node_a = rng.choice(paths_a)
    path_b, node_b = rng.choice(paths_b)

    new_a = _replace_subterm(a, path_a, node_b)
    new_b = _replace_subterm(b, path_b, node_a)
    return new_a, new_b


def annotate_genome(genome: Genome, **annotations: object) -> Genome:
    """Return a copy of ``genome`` with merged annotations.

    Existing annotations take lower precedence than the provided keys so that
    scoring and selection metadata can be layered deterministically without
    mutating the original payload.
    """

    merged = {**(genome.annotations or {}), **annotations}
    return Genome(root=genome.root, annotations=merged)


def evaluate_population(
    population: Sequence[Genome],
    scorer: Callable[[Genome], float | tuple[float, dict]],
    *,
    constraints: StructuralConstraints | None = None,
    violation_penalty: float | None = float("-inf"),
) -> list[Evaluation]:
    """Evaluate a population with a deterministic scorer.

    The scorer may return either a bare float or a ``(score, info)`` tuple to
    surface auxiliary metadata (e.g., constraint violations or bridge-derived
    metrics) without affecting ordering.
    """

    evaluations: list[Evaluation] = []
    for genome in population:
        violations = validate_structure(genome.root, constraints) if constraints else []

        result = scorer(genome)
        if isinstance(result, tuple):
            score, info = result
        else:
            score, info = result, None

        info = {**(info or {})}
        if violations:
            info.setdefault("violations", violations)
            if violation_penalty is not None:
                score = violation_penalty
        evaluations.append(Evaluation(genome=genome, score=score, info=info))
    evaluations.sort(key=lambda ev: ev.score, reverse=True)
    return evaluations


def _tournament_select(evaluations: Sequence[Evaluation], size: int, rng: random.Random) -> Evaluation:
    """Pick the best of ``size`` random candidates."""

    contenders = [rng.choice(evaluations) for _ in range(size)]
    return max(contenders, key=lambda ev: ev.score)


def evolve_population(
    population: Sequence[Genome],
    scorer: Callable[[Genome], float | tuple[float, dict]],
    mutate: Callable[[Genome, random.Random], Genome],
    *,
    crossover: Callable[[Genome, Genome, random.Random], tuple[Genome, Genome]] | None = None,
    config: EvolutionConfig,
    rng: random.Random | None = None,
    on_generation: Callable[[int, Evaluation, list[Evaluation]], None] | None = None,
) -> list[Evaluation]:
    """Run a deterministic evolutionary loop and return the final evaluations.

    The loop supports elitism, tournament selection, optional crossover, and
    per-generation callbacks for logging. All randomness flows through the
    provided ``rng`` to ensure reproducibility.
    """

    rng = rng or random.Random()
    current_population = list(population)

    for generation in range(config.generations):
        evaluations = evaluate_population(
            current_population,
            scorer,
            constraints=config.constraints,
            violation_penalty=config.violation_penalty,
        )
        best = evaluations[0]

        if on_generation:
            on_generation(generation, best, evaluations)

        next_population: list[Genome] = []
        elites = evaluations[: config.elitism]
        next_population.extend(
            annotate_genome(elite.genome, score=elite.score, generation=generation) for elite in elites
        )

        while len(next_population) < config.population_size:
            parent_a = _tournament_select(evaluations, config.tournament_size, rng)
            parent_b = _tournament_select(evaluations, config.tournament_size, rng)

            children: list[Genome] = [parent_a.genome]
            if crossover and rng.random() < config.crossover_rate:
                child_a, child_b = crossover(parent_a.genome, parent_b.genome, rng)
                children = [child_a, child_b]

            for child in children:
                mutated = mutate(child, rng) if rng.random() < config.mutation_rate else child
                next_population.append(annotate_genome(mutated, parent_score=parent_a.score))
                if len(next_population) >= config.population_size:
                    break

        current_population = next_population

    return evaluate_population(
        current_population,
        scorer,
        constraints=config.constraints,
        violation_penalty=config.violation_penalty,
    )

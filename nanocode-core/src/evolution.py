from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence, Tuple

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

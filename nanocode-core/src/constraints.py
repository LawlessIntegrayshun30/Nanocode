from __future__ import annotations

from dataclasses import dataclass
from dataclasses import dataclass
from typing import Iterable, Mapping

from src.terms import Term


@dataclass(frozen=True)
class StructuralMetrics:
    """Aggregate measurements of a Nanocode term tree.

    These metrics provide a deterministic footprint of a genome's shape and
    scale usage so evolutionary loops and validators can reason about
    complexity budgets.
    """

    nodes: int
    leaves: int
    max_depth: int
    max_fanout: int
    min_scale: int
    max_scale: int


@dataclass(frozen=True)
class StructuralConstraints:
    """Bounds that define a well-formed Nanocode genome structure."""

    max_nodes: int | None = None
    max_depth: int | None = None
    max_fanout: int | None = None
    min_scale: int | None = None
    max_scale: int | None = None


def constraints_to_dict(constraints: StructuralConstraints) -> dict:
    """Serialize constraints into a JSON-friendly mapping."""

    payload: dict[str, int] = {}
    if constraints.max_nodes is not None:
        payload["max_nodes"] = constraints.max_nodes
    if constraints.max_depth is not None:
        payload["max_depth"] = constraints.max_depth
    if constraints.max_fanout is not None:
        payload["max_fanout"] = constraints.max_fanout
    if constraints.min_scale is not None:
        payload["min_scale"] = constraints.min_scale
    if constraints.max_scale is not None:
        payload["max_scale"] = constraints.max_scale
    return payload


def constraints_from_dict(data: Mapping[str, object]) -> StructuralConstraints:
    """Deserialize constraints from a JSON-friendly mapping."""

    return StructuralConstraints(
        max_nodes=int(data["max_nodes"]) if "max_nodes" in data else None,
        max_depth=int(data["max_depth"]) if "max_depth" in data else None,
        max_fanout=int(data["max_fanout"]) if "max_fanout" in data else None,
        min_scale=int(data["min_scale"]) if "min_scale" in data else None,
        max_scale=int(data["max_scale"]) if "max_scale" in data else None,
    )


def _walk_terms(root: Term) -> Iterable[tuple[Term, int]]:
    stack: list[tuple[Term, int]] = [(root, 1)]
    while stack:
        term, depth = stack.pop()
        yield term, depth
        for child in reversed(term.children):
            stack.append((child, depth + 1))


def measure_structure(root: Term) -> StructuralMetrics:
    """Compute size/depth/fanout/scale metrics for a term tree."""

    nodes = 0
    leaves = 0
    max_depth = 0
    max_fanout = 0
    min_scale = root.scale
    max_scale = root.scale

    for term, depth in _walk_terms(root):
        nodes += 1
        if not term.children:
            leaves += 1
        max_depth = max(max_depth, depth)
        max_fanout = max(max_fanout, len(term.children))
        min_scale = min(min_scale, term.scale)
        max_scale = max(max_scale, term.scale)

    return StructuralMetrics(
        nodes=nodes,
        leaves=leaves,
        max_depth=max_depth,
        max_fanout=max_fanout,
        min_scale=min_scale,
        max_scale=max_scale,
    )


def validate_structure(root: Term, constraints: StructuralConstraints) -> list[str]:
    """Return human-readable violations of the provided constraints."""

    metrics = measure_structure(root)
    violations: list[str] = []

    if constraints.max_nodes is not None and metrics.nodes > constraints.max_nodes:
        violations.append(f"nodes={metrics.nodes} exceeds max_nodes={constraints.max_nodes}")
    if constraints.max_depth is not None and metrics.max_depth > constraints.max_depth:
        violations.append(f"max_depth={metrics.max_depth} exceeds max_depth={constraints.max_depth}")
    if constraints.max_fanout is not None and metrics.max_fanout > constraints.max_fanout:
        violations.append(
            f"max_fanout={metrics.max_fanout} exceeds max_fanout={constraints.max_fanout}"
        )
    if constraints.min_scale is not None and metrics.min_scale < constraints.min_scale:
        violations.append(f"min_scale={metrics.min_scale} below min_scale={constraints.min_scale}")
    if constraints.max_scale is not None and metrics.max_scale > constraints.max_scale:
        violations.append(f"max_scale={metrics.max_scale} exceeds max_scale={constraints.max_scale}")

    return violations

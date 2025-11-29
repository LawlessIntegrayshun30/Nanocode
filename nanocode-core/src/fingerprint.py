from __future__ import annotations

import hashlib
from typing import Iterable, TYPE_CHECKING

from src.constraints import constraints_to_dict
from src.rewrite import Action, Rule
from src.signature import Signature
from src.terms import Term

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from src.evolution import Genome


def _hash_components(parts: Iterable[str]) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fingerprint_term(term: Term) -> str:
    """Deterministic structural fingerprint for a ``Term`` tree."""

    child_hashes = [fingerprint_term(child) for child in term.children]
    return _hash_components([term.sym, str(term.scale), *child_hashes])


def fingerprint_rule(rule: Rule) -> str:
    """Fingerprint a rule without requiring serialization helpers."""

    action_name, params = _action_details(rule.action)
    pattern_sym = rule.pattern.sym if rule.pattern.sym is not None else "*"
    pattern_scale = "*" if rule.pattern.scale is None else str(rule.pattern.scale)
    predicate_flag = "1" if rule.pattern.predicate else "0"
    param_parts = [f"{key}={params[key]}" for key in sorted(params)]
    return _hash_components(
        [rule.name, pattern_sym, pattern_scale, predicate_flag, action_name, *param_parts]
    )


def fingerprint_program(program) -> str:
    """Fingerprint a program, capturing rules, budgets, constraints, and signature."""

    rule_hashes = [fingerprint_rule(rule) for rule in program.rules]
    constraint_fingerprint = _fingerprint_constraints(program.constraints)
    signature_fingerprint = _fingerprint_signature(program.signature)
    max_terms = "*" if program.max_terms is None else str(program.max_terms)
    return _hash_components(
        [
            program.name,
            fingerprint_term(program.root),
            str(program.max_steps),
            max_terms,
            constraint_fingerprint,
            signature_fingerprint,
            *rule_hashes,
        ]
    )


def fingerprint_genome(genome: "Genome") -> str:
    """Fingerprint a genome using its root structure and annotations."""

    annotation_parts: list[str] = []
    if genome.annotations:
        annotation_parts = [f"{k}={genome.annotations[k]}" for k in sorted(genome.annotations)]

    return _hash_components(["genome", fingerprint_term(genome.root), *annotation_parts])


def _action_details(action) -> tuple[str, dict[str, object]]:
    if isinstance(action, Action):
        return action.name, dict(action.params)
    name = getattr(action, "name", None) or getattr(action, "__name__", action.__class__.__name__)
    return name, {}


def _fingerprint_constraints(constraints) -> str:
    if constraints is None:
        return "constraints:none"
    payload = constraints_to_dict(constraints)
    parts = [f"{k}={payload[k]}" for k in sorted(payload) if payload[k] is not None]
    return _hash_components(["constraints", *parts])


def _fingerprint_signature(signature: Signature | None) -> str:
    if signature is None:
        return "signature:none"
    payload = signature.to_dict()
    parts: list[str] = []
    for sym, entry in sorted(payload.get("symbols", {}).items()):
        scales = entry.get("scales")
        scales_text = ",".join(str(s) for s in scales) if scales is not None else "*"
        parts.append(
            f"{sym}:{entry['min_children']}:{entry.get('max_children')}:scales={scales_text}"
        )
    return _hash_components(["signature", *parts])

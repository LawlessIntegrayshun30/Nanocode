from __future__ import annotations

from typing import Callable, Iterable, Optional

from src.constraints import StructuralConstraints
from src.interpreter import Program, validate_program
from src.rewrite import Action, Pattern, Rule, action_from_spec
from src.signature import Signature, TermSignature
from src.terms import Term


def _child_by_sym(term: Term, sym: str) -> Optional[Term]:
    for child in term.children:
        if child.sym == sym:
            return child
    return None


def _value_to_term(value: object) -> Term:
    if isinstance(value, (int, float, bool)):
        return Term(sym=str(value))
    if isinstance(value, str):
        return Term(sym=value)
    raise TypeError(f"Unsupported parameter type for meta serialization: {type(value)}")


def _value_from_term(term: Term) -> object:
    if term.children:
        raise ValueError("Value terms must not have children")
    text = term.sym
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    if text in {"True", "False"}:
        return text == "True"
    return text


def pattern_to_term(pattern: Pattern) -> Term:
    return Term(
        sym="pattern",
        children=[
            Term(sym="sym", children=[Term(sym=pattern.sym)]) if pattern.sym is not None else Term(sym="sym"),
            Term(sym="scale", children=[Term(sym=str(pattern.scale))]) if pattern.scale is not None else Term(sym="scale"),
        ],
    )


def term_to_pattern(term: Term) -> Pattern:
    if term.sym != "pattern":
        raise ValueError(f"Expected pattern term, got {term.sym}")

    sym_child = _child_by_sym(term, "sym")
    scale_child = _child_by_sym(term, "scale")

    sym_value = sym_child.children[0].sym if sym_child and sym_child.children else None
    scale_value = None
    if scale_child and scale_child.children:
        scale_value = int(_value_from_term(scale_child.children[0]))

    return Pattern(sym=sym_value, scale=scale_value)


def action_to_term(action: Action) -> Term:
    if not isinstance(action, Action):
        raise TypeError("Only Action instances can be serialized to terms")

    param_terms = [
        Term(sym=key, children=[_value_to_term(value)]) for key, value in sorted(action.params.items())
    ]

    return Term(
        sym="action",
        children=[
            Term(sym="name", children=[Term(sym=action.name)]),
            Term(sym="params", children=param_terms),
        ],
    )


def term_to_action(
    term: Term, summarizers: dict[str, Callable[[list[Term]], str]] | None = None
) -> Action:
    if term.sym != "action":
        raise ValueError(f"Expected action term, got {term.sym}")

    name_term = _child_by_sym(term, "name")
    params_term = _child_by_sym(term, "params")
    if not name_term or not name_term.children:
        raise ValueError("Action term missing name child")

    name = name_term.children[0].sym
    params: dict[str, object] = {}
    if params_term:
        for param in params_term.children:
            if not param.children:
                continue
            params[param.sym] = _value_from_term(param.children[0])

    return action_from_spec(name, params, summarizers=summarizers)


def _constraints_to_term(constraints: StructuralConstraints) -> Term:
    children: list[Term] = []
    if constraints.max_nodes is not None:
        children.append(Term(sym="max_nodes", children=[_value_to_term(constraints.max_nodes)]))
    if constraints.max_depth is not None:
        children.append(Term(sym="max_depth", children=[_value_to_term(constraints.max_depth)]))
    if constraints.max_fanout is not None:
        children.append(Term(sym="max_fanout", children=[_value_to_term(constraints.max_fanout)]))
    if constraints.min_scale is not None:
        children.append(Term(sym="min_scale", children=[_value_to_term(constraints.min_scale)]))
    if constraints.max_scale is not None:
        children.append(Term(sym="max_scale", children=[_value_to_term(constraints.max_scale)]))

    return Term(sym="constraints", children=children)


def _constraints_from_term(term: Term) -> StructuralConstraints:
    if term.sym != "constraints":
        raise ValueError(f"Expected constraints term, got {term.sym}")

    kwargs: dict[str, int | None] = {
        "max_nodes": None,
        "max_depth": None,
        "max_fanout": None,
        "min_scale": None,
        "max_scale": None,
    }

    for child in term.children:
        if not child.children:
            continue
        kwargs[child.sym] = int(_value_from_term(child.children[0]))

    return StructuralConstraints(**kwargs)


def _signature_to_term(signature: Signature) -> Term:
    entries: list[Term] = []
    for sym, entry in signature.items():
        entry_children = [
            Term(sym="name", children=[Term(sym=sym)]),
            Term(sym="min_children", children=[_value_to_term(entry.min_children)]),
        ]
        if entry.max_children is not None:
            entry_children.append(Term(sym="max_children", children=[_value_to_term(entry.max_children)]))
        else:
            entry_children.append(Term(sym="max_children"))

        if entry.allowed_scales is not None:
            entry_children.append(
                Term(sym="scales", children=[_value_to_term(scale) for scale in sorted(entry.allowed_scales)])
            )
        else:
            entry_children.append(Term(sym="scales"))

        entries.append(Term(sym="symbol", children=entry_children))

    return Term(sym="signature", children=entries)


def _signature_from_term(term: Term) -> Signature:
    if term.sym != "signature":
        raise ValueError(f"Expected signature term, got {term.sym}")

    entries: list[TermSignature] = []
    for child in term.children:
        if child.sym != "symbol":
            continue
        name_child = _child_by_sym(child, "name")
        if not name_child or not name_child.children:
            raise ValueError("Signature entry missing symbol name")
        min_children_child = _child_by_sym(child, "min_children")
        max_children_child = _child_by_sym(child, "max_children")
        scales_child = _child_by_sym(child, "scales")

        allowed_scales = None
        if scales_child and scales_child.children:
            allowed_scales = {int(_value_from_term(scale_term)) for scale_term in scales_child.children}

        entries.append(
            TermSignature(
                sym=name_child.children[0].sym,
                min_children=int(_value_from_term(min_children_child.children[0])) if min_children_child and min_children_child.children else 0,
                max_children=(
                    int(_value_from_term(max_children_child.children[0]))
                    if max_children_child and max_children_child.children
                    else None
                ),
                allowed_scales=allowed_scales,
            )
        )

    return Signature(entries)


def rule_to_term(rule: Rule) -> Term:
    return Term(
        sym="rule",
        children=[
            Term(sym="name", children=[Term(sym=rule.name)]),
            pattern_to_term(rule.pattern),
            action_to_term(rule.action),
        ],
    )


def term_to_rule(
    term: Term, summarizers: dict[str, Callable[[list[Term]], str]] | None = None
) -> Rule:
    if term.sym != "rule":
        raise ValueError(f"Expected rule term, got {term.sym}")

    name_child = _child_by_sym(term, "name")
    if not name_child or not name_child.children:
        raise ValueError("Rule term missing name child")

    pattern_child = next((c for c in term.children if c.sym == "pattern"), None)
    action_child = next((c for c in term.children if c.sym == "action"), None)
    if pattern_child is None or action_child is None:
        raise ValueError("Rule term missing pattern or action")

    return Rule(
        name=name_child.children[0].sym,
        pattern=term_to_pattern(pattern_child),
        action=term_to_action(action_child, summarizers=summarizers),
    )


def program_to_term(program: Program) -> Term:
    rules_term = Term(sym="rules", children=[rule_to_term(rule) for rule in program.rules])
    config_children = [
        Term(sym="name", children=[Term(sym=program.name)]),
        Term(sym="root", children=[program.root]),
        rules_term,
        Term(sym="max_steps", children=[Term(sym=str(program.max_steps))]),
        Term(sym="max_terms", children=[Term(sym=str(program.max_terms))]) if program.max_terms is not None else Term(sym="max_terms"),
    ]

    if program.constraints is not None:
        config_children.append(_constraints_to_term(program.constraints))
    if program.signature is not None:
        config_children.append(_signature_to_term(program.signature))

    return Term(sym="program", children=config_children)


def term_to_program(
    term: Term, summarizers: dict[str, Callable[[list[Term]], str]] | None = None
) -> Program:
    if term.sym != "program":
        raise ValueError(f"Expected program term, got {term.sym}")

    name_child = _child_by_sym(term, "name")
    root_child = _child_by_sym(term, "root")
    rules_child = _child_by_sym(term, "rules")
    steps_child = _child_by_sym(term, "max_steps")
    max_terms_child = _child_by_sym(term, "max_terms")
    constraints_child = _child_by_sym(term, "constraints")
    signature_child = _child_by_sym(term, "signature")

    if not name_child or not name_child.children:
        raise ValueError("Program term missing name")
    if not root_child or not root_child.children:
        raise ValueError("Program term missing root")
    if not rules_child:
        raise ValueError("Program term missing rules")

    rules = [term_to_rule(rule_term, summarizers=summarizers) for rule_term in rules_child.children]
    max_steps = int(_value_from_term(steps_child.children[0])) if steps_child and steps_child.children else 256
    max_terms = None
    if max_terms_child and max_terms_child.children:
        max_terms = int(_value_from_term(max_terms_child.children[0]))

    constraints = _constraints_from_term(constraints_child) if constraints_child else None
    signature = _signature_from_term(signature_child) if signature_child else None

    program = Program(
        name=name_child.children[0].sym,
        root=root_child.children[0],
        rules=rules,
        max_steps=max_steps,
        max_terms=max_terms,
        constraints=constraints,
        signature=signature,
    )
    validate_program(program)
    return program


def rules_to_term(rules: Iterable[Rule]) -> Term:
    return Term(sym="rules", children=[rule_to_term(rule) for rule in rules])


def term_to_rules(
    term: Term, summarizers: dict[str, Callable[[list[Term]], str]] | None = None
) -> list[Rule]:
    if term.sym != "rules":
        raise ValueError(f"Expected rules term, got {term.sym}")
    return [term_to_rule(child, summarizers=summarizers) for child in term.children]


def constraints_to_term(constraints: StructuralConstraints) -> Term:
    return _constraints_to_term(constraints)


def term_to_constraints(term: Term) -> StructuralConstraints:
    return _constraints_from_term(term)


def signature_to_term(signature: Signature) -> Term:
    return _signature_to_term(signature)


def term_to_signature(term: Term) -> Signature:
    return _signature_from_term(term)

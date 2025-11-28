from __future__ import annotations

from typing import Iterable, Optional

from src.interpreter import Program, validate_program
from src.rewrite import Action, Pattern, Rule, action_from_spec
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


def term_to_action(term: Term) -> Action:
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

    return action_from_spec(name, params)


def rule_to_term(rule: Rule) -> Term:
    return Term(
        sym="rule",
        children=[
            Term(sym="name", children=[Term(sym=rule.name)]),
            pattern_to_term(rule.pattern),
            action_to_term(rule.action),
        ],
    )


def term_to_rule(term: Term) -> Rule:
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
        action=term_to_action(action_child),
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

    return Term(sym="program", children=config_children)


def term_to_program(term: Term) -> Program:
    if term.sym != "program":
        raise ValueError(f"Expected program term, got {term.sym}")

    name_child = _child_by_sym(term, "name")
    root_child = _child_by_sym(term, "root")
    rules_child = _child_by_sym(term, "rules")
    steps_child = _child_by_sym(term, "max_steps")
    max_terms_child = _child_by_sym(term, "max_terms")

    if not name_child or not name_child.children:
        raise ValueError("Program term missing name")
    if not root_child or not root_child.children:
        raise ValueError("Program term missing root")
    if not rules_child:
        raise ValueError("Program term missing rules")

    rules = [term_to_rule(rule_term) for rule_term in rules_child.children]
    max_steps = int(_value_from_term(steps_child.children[0])) if steps_child and steps_child.children else 256
    max_terms = None
    if max_terms_child and max_terms_child.children:
        max_terms = int(_value_from_term(max_terms_child.children[0]))

    program = Program(
        name=name_child.children[0].sym,
        root=root_child.children[0],
        rules=rules,
        max_steps=max_steps,
        max_terms=max_terms,
    )
    validate_program(program)
    return program


def rules_to_term(rules: Iterable[Rule]) -> Term:
    return Term(sym="rules", children=[rule_to_term(rule) for rule in rules])


def term_to_rules(term: Term) -> list[Rule]:
    if term.sym != "rules":
        raise ValueError(f"Expected rules term, got {term.sym}")
    return [term_to_rule(child) for child in term.children]

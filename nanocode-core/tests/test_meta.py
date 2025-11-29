import pytest

from src.interpreter import Program
from src.meta import (
    action_to_term,
    program_to_term,
    rule_to_term,
    term_to_action,
    term_to_program,
    term_to_rule,
)
from src.rewrite import Pattern, Rule, expand_action, reduce_action
from src.terms import Term


def test_program_roundtrip_preserves_rules_and_actions():
    rules = [
        Rule(name="grow", pattern=Pattern(sym="seed", scale=0), action=expand_action(fanout=2)),
        Rule(name="shrink", pattern=Pattern(scale=1), action=reduce_action()),
    ]
    program = Program(name="demo", root=Term("seed"), rules=rules, max_steps=32, max_terms=10)

    program_term = program_to_term(program)
    rebuilt = term_to_program(program_term)

    assert rebuilt.name == program.name
    assert rebuilt.root == program.root
    assert rebuilt.max_steps == program.max_steps
    assert rebuilt.max_terms == program.max_terms
    assert [rule.name for rule in rebuilt.rules] == [rule.name for rule in rules]
    assert rebuilt.rules[0].pattern.sym == "seed"
    assert rebuilt.rules[0].action.name == "expand"
    assert rebuilt.rules[0].action.params["fanout"] == 2
    assert rebuilt.rules[1].pattern.scale == 1
    assert rebuilt.rules[1].action.name == "reduce"


def test_rule_and_action_terms_require_metadata_actions():
    action = expand_action(fanout=4)
    rule = Rule(name="grow", pattern=Pattern(sym="seed"), action=action)

    roundtrip_rule = term_to_rule(rule_to_term(rule))
    assert roundtrip_rule.action.name == "expand"
    assert roundtrip_rule.action.params["fanout"] == 4

    with pytest.raises(TypeError):
        action_to_term(lambda t, s: t)  # type: ignore[arg-type]


def test_action_term_rejects_unknown_names():
    bad_term = Term(sym="action", children=[Term(sym="name", children=[Term(sym="unknown")])])
    with pytest.raises(ValueError):
        term_to_action(bad_term)


def test_reduce_action_roundtrip_requires_registered_summarizer():
    def summarize(children: list[Term]) -> str:
        return f"span={len(children)}"

    rule = Rule(name="shrink", pattern=Pattern(sym="x"), action=reduce_action(summarizer=summarize))
    rule_term = rule_to_term(rule)

    with pytest.raises(ValueError):
        term_to_rule(rule_term)

    restored = term_to_rule(rule_term, summarizers={"summarize": summarize})
    assert restored.action.name == "reduce"
    assert restored.action.params["summarizer"] == "summarize"


from src.fingerprint import fingerprint_program, fingerprint_rule, fingerprint_term
from src.interpreter import Program
from src.rewrite import Pattern, Rule
from src.terms import Term


def test_fingerprint_term_is_deterministic():
    term = Term("root", 0, children=[Term("leaf", 1)])
    assert fingerprint_term(term) == fingerprint_term(term)


def test_fingerprint_program_reflects_structure_changes():
    rule = Rule(name="grow", pattern=Pattern(sym="seed"), action=lambda t, _: t)
    base = Program(name="demo", root=Term("seed", 0), rules=[rule])

    digest = fingerprint_program(base)
    tweaked = Program(name="demo", root=Term("seed", 0, children=[Term("child", 1)]), rules=[rule])
    assert digest != fingerprint_program(tweaked)


def test_fingerprint_rule_changes_with_name_or_pattern():
    base = Rule(name="a", pattern=Pattern(sym="x"), action=lambda t, _: t)
    renamed = Rule(name="b", pattern=Pattern(sym="x"), action=lambda t, _: t)
    assert fingerprint_rule(base) != fingerprint_rule(renamed)

import pytest

from src import Interpreter
from src.ast import parse_program, parse_rule, parse_term
from src.runtime import Runtime


def test_parse_term_with_scale_and_children():
    term = parse_term(["root", ":scale", 2, ["child"], ["leaf", ["bud"]]])
    assert term.sym == "root"
    assert term.scale == 2
    assert len(term.children) == 2
    assert term.children[0].sym == "child"
    assert term.children[1].children[0].sym == "bud"


def test_parse_rule_expand_fanout():
    rule = parse_rule([
        "rule",
        "expand-root",
        ["pattern", ":sym", "seed"],
        ["action", "expand", ":fanout", 2],
    ])
    term = parse_term("seed")
    runtime = Runtime([rule])
    runtime.load(term)
    event = runtime.step()
    assert event is not None
    assert event.after_term.sym == "F(seed)"
    assert len(event.after_term.children) == 2


def test_parse_program_runs_via_interpreter():
    program_source = """
    (program demo
      (root (seed))
      (rules
        (rule expand-seed
          (pattern :sym seed :scale 0)
          (action expand :fanout 2))
        (rule reduce-seed
          (pattern :sym F(seed) :scale 1)
          (action reduce)))
      (max_steps 4))
    """

    program = parse_program(program_source)
    result = Interpreter().run(program)

    assert result.root_id is not None
    # Expect an expand followed by a reduce
    assert len(result.events) == 2
    assert result.events[0].after_term.sym == "F(seed)"
    assert result.events[1].after_term.sym == "seed"
    assert result.snapshot["root"] == result.root_id


def test_parse_program_rejects_duplicate_rule_names():
    program_source = """
    (program dup-rules
      (root (seed))
      (rules
        (rule same-name (pattern :sym seed) (action expand :fanout 1))
        (rule same-name (pattern :sym seed :scale 1) (action reduce))))
    """

    with pytest.raises(ValueError, match="Duplicate rule name"):
        parse_program(program_source)


def test_parse_program_rejects_negative_scales():
    program_source = """
    (program negative-scale
      (root (seed :scale -1))
      (rules
        (rule expand-seed (pattern :sym seed) (action expand :fanout 1))))
    """

    with pytest.raises(ValueError, match="negative scale"):
        parse_program(program_source)

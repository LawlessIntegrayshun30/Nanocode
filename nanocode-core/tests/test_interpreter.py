from src.interpreter import Execution, Interpreter, Program
from src.rewrite import Pattern, Rule
from src import terms


def expand_leaf(term: terms.Term, _store) -> terms.Term:
    return terms.expand(term, fanout=2)


def reduce_wrapper(term: terms.Term, _store) -> terms.Term:
    return terms.reduce(term)


def test_interpreter_runs_to_idle_and_records_snapshot():
    program = Program(
        name="expand_reduce",
        root=terms.Term("Seed", 0),
        rules=[
            Rule(name="expand", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
            Rule(name="reduce", pattern=Pattern(predicate=lambda t: t.sym.startswith("F(")), action=reduce_wrapper),
        ],
        max_steps=8,
    )

    result: Execution = Interpreter().run(program)

    assert result.root_id == result.snapshot["root"]
    assert [e.rule for e in result.events] == ["expand", "reduce"]
    # The store should retain the interned root and the expanded variant.
    assert len(result.snapshot["records"]) >= 2
    assert result.stats["rule_counts"] == {"expand": 1, "reduce": 1}


def test_run_until_idle_honors_step_budget():
    program = Program(
        name="one_step",
        root=terms.Term("A", 0),
        rules=[Rule(name="expand", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf)],
        max_steps=1,
    )

    interpreter = Interpreter()
    result = interpreter.run(program)

    assert len(result.events) == 1
    # New work remains on the frontier because we stopped early.
    assert len(result.snapshot["frontier"]) == 1


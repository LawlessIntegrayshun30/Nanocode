import pytest

from src import terms
from src.rewrite import AmbiguousRuleError, Pattern, Rule
from src.runtime import Runtime


def expand_leaf(term: terms.Term, _store) -> terms.Term:
    return terms.expand(term, fanout=2)


def reduce_f_term(term: terms.Term, _store) -> terms.Term:
    return terms.reduce(term)


def test_runtime_applies_rules_and_logs_events():
    rules = [
        Rule(name="expand_leaf", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
        Rule(name="reduce_f", pattern=Pattern(predicate=lambda t: t.sym.startswith("F(")), action=reduce_f_term),
    ]

    runtime = Runtime(rules=rules)
    root_id = runtime.load(terms.Term("A", 0))

    events = runtime.run(max_steps=3)

    assert len(events) == 2
    assert events[0].before == root_id
    assert events[0].rule == "expand_leaf"
    assert events[1].rule == "reduce_f"

    # After reduce, we should get back to the interned root ID (deduplication)
    assert events[1].after == root_id


def test_runtime_skips_unmatched_terms_but_keeps_running():
    rules = [Rule(name="only_b", pattern=Pattern(sym="B"), action=lambda t, _: t)]

    runtime = Runtime(rules=rules)
    runtime.load(terms.Term("A", 0))
    b_id = runtime.store.add_term(terms.Term("B", 0))
    runtime.scheduler.push(b_id)

    events = runtime.run(max_steps=2)

    assert len(events) == 1
    assert events[0].before == b_id


def test_runtime_load_resets_state():
    runtime = Runtime(rules=[])

    first_root = runtime.load(terms.Term("X", 0))
    runtime.run(max_steps=1)

    second_root = runtime.load(terms.Term("Y", 0))

    assert runtime.root_id == second_root
    assert first_root != second_root
    assert len(runtime.store.snapshot()) == 1
    assert runtime.events == []


def test_runtime_optionally_walks_children():
    rules = [
        Rule(
            name="expand_shallow_leaves",
            pattern=Pattern(predicate=lambda t: not t.children and t.scale < 2),
            action=lambda t, _: terms.expand(t, fanout=2),
        )
    ]

    runtime = Runtime(rules=rules, walk_children=True)
    runtime.load(terms.Term("seed", 0))

    events = runtime.run_until_idle(max_steps=20)

    expanded_symbols = {event.before_term.sym for event in events}
    assert "seed" in expanded_symbols
    # With child walking enabled, grandchildren participate in rewriting.
    assert any(sym.startswith("seed.0") or sym.startswith("seed.1") for sym in expanded_symbols)


def test_runtime_can_fail_on_ambiguous_matches():
    rules = [
        Rule(name="first", pattern=Pattern(sym="seed"), action=lambda t, _: terms.expand(t, fanout=1)),
        Rule(name="second", pattern=Pattern(sym="seed"), action=lambda t, _: t),
    ]

    runtime = Runtime(rules=rules, strict_matching=True)
    runtime.load(terms.Term("seed", 0))

    with pytest.raises(AmbiguousRuleError) as excinfo:
        runtime.step()

    message = str(excinfo.value)
    assert "ambiguous match" in message
    assert "first" in message and "second" in message

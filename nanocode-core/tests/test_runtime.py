import pytest

from src import terms
from src.rewrite import AmbiguousRuleError, Pattern, Rule
from src.runtime import Runtime
from src.term_store import TermStore
from src.scheduler import LIFOScheduler


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


def test_runtime_respects_walk_depth_limit():
    rules = [
        Rule(
            name="mark_targets",
            pattern=Pattern(sym="target"),
            action=lambda t, _: terms.Term(f"marked-{t.sym}", t.scale, t.children),
        )
    ]

    root = terms.Term("root", 0, children=[terms.Term("mid", 0, children=[terms.Term("target", 0)])])

    shallow = Runtime(rules=rules, walk_children=True, walk_depth=1)
    shallow.load(root)
    shallow_events = shallow.run_until_idle(max_steps=5)
    assert len(shallow_events) == 0

    deep = Runtime(rules=rules, walk_children=True, walk_depth=2)
    deep.load(root)
    deep_events = deep.run_until_idle(max_steps=5)
    assert len(deep_events) == 1
    assert deep_events[0].after_term.sym.startswith("marked-target")


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


def test_runtime_tracks_rule_and_scale_counts():
    rules = [
        Rule(name="expand", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
        Rule(name="reduce", pattern=Pattern(predicate=lambda t: t.sym.startswith("F(")), action=reduce_f_term),
    ]

    runtime = Runtime(rules=rules, walk_children=False)
    runtime.load(terms.Term("seed", 1))

    runtime.run_until_idle(max_steps=4)

    stats = runtime.stats()

    assert stats["events"] == 2
    assert stats["rule_counts"] == {"expand": 1, "reduce": 1}
    # Expand bumps scale to 2 for the intermediate node; reduce acts at that scale.
    assert stats["scale_counts"] == {1: 1, 2: 1}
    assert stats["store_size"] >= 2
    assert stats["idle"] is True
    assert stats["budget_exhausted"] is False


def test_runtime_honors_custom_scheduler_ordering():
    rules = [Rule(name="mark", pattern=Pattern(), action=lambda t, _: t)]

    runtime = Runtime(rules=rules, scheduler=LIFOScheduler(), walk_children=True)
    runtime.load(terms.Term("root", 0, children=[terms.Term("left"), terms.Term("right")]))

    events = runtime.run_until_idle(max_steps=5)
    seen = [event.before_term.sym for event in events]

    # LIFO scheduling reverses the initial push order: right, left, root.
    assert seen[:3] == ["right", "left", "root"]


def test_runtime_reports_budget_exhaustion_when_work_remains():
    rules = [
        Rule(name="expand", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
        Rule(name="reduce", pattern=Pattern(predicate=lambda t: t.sym.startswith("F(")), action=reduce_f_term),
    ]

    runtime = Runtime(rules=rules, walk_children=False)
    runtime.load(terms.Term("seed", 0))

    runtime.run(max_steps=1)

    stats = runtime.stats()
    assert stats["budget_exhausted"] is True
    assert stats["idle"] is False
    assert stats["frontier"]

    runtime.run_until_idle(max_steps=10)

    completed = runtime.stats()
    assert completed["budget_exhausted"] is False
    assert completed["idle"] is True


def test_runtime_respects_rule_budgets():
    rules = [
        Rule(name="grow", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
    ]

    runtime = Runtime(rules=rules, walk_children=True, rule_budgets={"grow": 1})
    runtime.load(terms.Term("root", 0, children=[terms.Term("left"), terms.Term("right")]))

    runtime.run_until_idle(max_steps=10)

    stats = runtime.stats()
    assert stats["rule_counts"] == {"grow": 1}
    assert stats["rule_budget_exhausted"] == ["grow"]
    # Only the first leaf is rewritten due to the budget cap, leaving work idle but processed.
    assert stats["events"] == 1


def test_runtime_halts_when_term_limit_exhausted():
    rules = [
        Rule(name="grow", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
    ]

    runtime = Runtime(rules=rules, walk_children=False, max_terms=1)
    runtime.load(terms.Term("root", 0))

    runtime.run_until_idle(max_steps=10)

    stats = runtime.stats()
    assert stats["events"] == 1
    assert stats["term_limit_exhausted"] is True
    # The store should have more terms than allowed, reflecting the point of exhaustion.
    assert stats["store_size"] > runtime.max_terms


def test_runtime_filters_rules_by_include_and_exclude():
    rules = [
        Rule(name="expand", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
        Rule(name="reduce", pattern=Pattern(predicate=lambda t: t.sym.startswith("F(")), action=reduce_f_term),
    ]

    runtime = Runtime(rules=rules, include_rules=["expand"], exclude_rules=["reduce"])
    runtime.load(terms.Term("seed", 0))

    runtime.run_until_idle(max_steps=5)

    stats = runtime.stats()
    assert stats["rule_counts"] == {"expand": 1}
    # Reduce is excluded even though it would match the expanded term.
    assert stats["events"] == 1
    assert "reduce" not in stats["rule_counts"]


def test_runtime_filters_terms_by_scale():
    rules = [
        Rule(name="scale0", pattern=Pattern(scale=0), action=lambda t, _: terms.expand(t, fanout=1)),
        Rule(name="scale1", pattern=Pattern(scale=1), action=lambda t, _: terms.expand(t, fanout=1)),
    ]

    root = terms.Term("root", 0, children=[terms.Term("leaf", 1)])

    runtime = Runtime(rules=rules, include_scales=[1], walk_children=True)
    runtime.load(root)

    runtime.run_until_idle(max_steps=5)

    stats = runtime.stats()
    assert stats["events"] == 1
    assert stats["rule_counts"] == {"scale1": 1}
    assert stats["scale_counts"] == {1: 1}


def test_runtime_can_restore_serialized_state():
    rules = [
        Rule(name="grow", pattern=Pattern(sym="seed"), action=lambda t, _: terms.expand(t, fanout=1)),
        Rule(name="normalize", pattern=Pattern(sym="F(seed)"), action=lambda t, _: terms.reduce(t)),
    ]

    runtime = Runtime(rules=rules)
    runtime.load(terms.Term("seed", 0))
    runtime.run(max_steps=1)

    state = runtime.state()
    restored = Runtime(rules=rules)
    store = TermStore.from_json(state)
    restored.load_state(
        store=store,
        root_id=state["root"],
        frontier=state.get("frontier"),
        processed=state.get("processed"),
    )

    restored.run_until_idle(max_steps=5)

    stats = restored.stats()
    assert stats["events"] == 1
    assert stats["rule_counts"] == {"normalize": 1}
    assert stats["frontier"] == []


def test_runtime_can_detect_conflicting_rules():
    rules = [
        Rule(name="a", pattern=Pattern(sym="X", scale=0), action=lambda t, s: t),
        Rule(name="b", pattern=Pattern(sym="X", scale=0), action=lambda t, s: t),
    ]

    with pytest.raises(ValueError):
        Runtime(rules=rules, detect_conflicts=True)

    runtime = Runtime(rules=rules, detect_conflicts=False)
    runtime.load(terms.Term("X", 0))

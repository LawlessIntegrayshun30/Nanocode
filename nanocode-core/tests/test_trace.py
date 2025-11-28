import io
import json

from src import terms
from src.rewrite import Pattern, Rule
from src.runtime import Runtime
from src.trace import JSONLTracer, dump_events


def expand_leaf(term: terms.Term, _store) -> terms.Term:
    return terms.expand(term, fanout=2)


def reduce_f_term(term: terms.Term, _store) -> terms.Term:
    return terms.reduce(term)


def test_jsonl_tracer_captures_runtime_events():
    rules = [
        Rule(name="expand_leaf", pattern=Pattern(predicate=lambda t: not t.children), action=expand_leaf),
        Rule(name="reduce_f", pattern=Pattern(predicate=lambda t: t.sym.startswith("F(")), action=reduce_f_term),
    ]

    sink = io.StringIO()
    tracer = JSONLTracer(sink)

    runtime = Runtime(rules=rules, event_hooks=[tracer])
    root_id = runtime.load(terms.Term("A", 0))
    runtime.run(max_steps=3)

    lines = [l for l in sink.getvalue().splitlines() if l]
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["before"] == root_id
    assert first["rule"] == "expand_leaf"
    assert first["after_term"]["sym"].startswith("F(")


def test_dump_events_serializes_event_stream():
    rule = Rule(name="echo", pattern=Pattern(predicate=lambda _t: True), action=lambda t, _s: t)
    runtime = Runtime([rule])
    runtime.load(terms.Term("Z", 0))
    events = runtime.run(max_steps=1)

    records = dump_events(events)
    assert records[0]["before_term"]["sym"] == "Z"
    assert records[0]["after_term"]["sym"] == "Z"

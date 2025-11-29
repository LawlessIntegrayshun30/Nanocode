from src.pipeline import make_text_program, run_pipeline
from src.interpreter import Interpreter


def test_pipeline_program_runs_multiscale():
    program = make_text_program("abba")
    execution = Interpreter().run(program)
    final = execution.materialize_root()
    assert final.sym in {"text", "F(text)"}
    # Summary child reflects dominant motif
    def _flatten(term):
        if not term.children:
            yield term.sym
        for child in term.children:
            yield from _flatten(child)

    assert any("dominant=" in sym for sym in _flatten(final))
    # Both expand and reduce should have fired
    assert set(execution.stats["rule_counts"].keys()) == {"to-meso", "to-macro"}


def test_run_pipeline_wrapper_returns_macro_term():
    result = run_pipeline("abc")
    assert result.sym in {"text", "F(text)"}
    assert result.children

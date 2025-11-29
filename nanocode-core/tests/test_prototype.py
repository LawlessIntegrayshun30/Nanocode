import json
import subprocess
from pathlib import Path

from src.prototype import run_prototype


def test_prototype_program_materializes_macro_label(tmp_path: Path):
    execution = run_prototype("nanocode", trace=tmp_path / "trace.jsonl", store=tmp_path / "store.json")
    final_term = execution.materialize_root()

    assert final_term.scale == 2
    macro = next(child for child in final_term.children if child.sym.startswith("port:out:macro"))
    macro_label = macro.children[0].sym
    assert any(macro_label.startswith(prefix) for prefix in ("vowel-heavy", "consonant-heavy", "mixed"))
    assert "len=" in macro_label

    trace = (tmp_path / "trace.jsonl").read_text().strip().splitlines()
    assert trace, "trace should contain events"

    stored = json.loads((tmp_path / "store.json").read_text())
    assert stored["root"] == execution.snapshot["root"]


def test_prototype_cli_runs(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    store_path = tmp_path / "store.json"
    result = subprocess.run(
        ["python", "-m", "src.prototype", "--text", "aeiou", "--trace-jsonl", str(trace_path), "--store-json", str(store_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["macro_label"].startswith("vowel-heavy")
    assert trace_path.exists()
    assert store_path.exists()
    # final term should surface the macro port tag
    assert any(child["sym"].startswith("port:out:macro") for child in payload["final_term"]["children"])

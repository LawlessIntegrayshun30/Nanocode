import json
import subprocess
import sys
from pathlib import Path


def test_cli_runs_program(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0))
      (rules
        (rule grow (pattern :sym seed) (action expand :fanout 2))
        (rule normalize (pattern :sym F(seed)) (action reduce))
      )
      (max_steps 4)
    )
    """

    program_file = tmp_path / "demo.nanocode"
    program_file.write_text(program_src)
    trace_file = tmp_path / "trace.jsonl"

    result = subprocess.run(
        [sys.executable, "-m", "src.cli", str(program_file), "--trace-jsonl", str(trace_file)],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["program"] == "demo"
    assert summary["events"] > 0
    assert trace_file.exists()
    trace_lines = trace_file.read_text().strip().splitlines()
    assert len(trace_lines) == summary["events"]


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
    assert summary["rule_counts"]
    assert summary["scale_counts"]
    assert trace_file.exists()
    trace_lines = trace_file.read_text().strip().splitlines()
    assert len(trace_lines) == summary["events"]


def test_cli_accepts_stdin(tmp_path: Path):
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

    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "-"],
        check=True,
        capture_output=True,
        text=True,
        input=program_src,
    )

    summary = json.loads(result.stdout)
    assert summary["program"] == "demo"
    assert summary["events"] > 0
    assert summary["rule_counts"]


def test_cli_strict_matching_fails_on_ambiguity(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0))
      (rules
        (rule first (pattern :sym seed) (action expand :fanout 1))
        (rule second (pattern :sym seed) (action reduce))
      )
      (max_steps 2)
    )
    """

    program_file = tmp_path / "ambiguous.nanocode"
    program_file.write_text(program_src)

    result = subprocess.run(
        [sys.executable, "-m", "src.cli", str(program_file), "--strict-matching"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "ambiguous match" in result.stderr


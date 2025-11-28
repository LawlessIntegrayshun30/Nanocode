import json
import subprocess
import sys
from pathlib import Path


def test_cli_runs_program(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0 (seed :scale 0) (seed :scale 0)))
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
    assert summary["scheduler"] == "fifo"
    assert summary["walk_children"] is False
    assert summary["strict_matching"] is False
    assert summary["events"] > 0
    assert summary["rule_counts"]
    assert summary["scale_counts"]
    assert summary["idle"] is True
    assert summary["budget_exhausted"] is False
    assert trace_file.exists()
    trace_lines = trace_file.read_text().strip().splitlines()
    assert len(trace_lines) == summary["events"]


def test_cli_accepts_scheduler_override(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0 (child1) (child2)))
      (rules
        (rule mark (pattern) (action reduce))
      )
      (max_steps 3)
    )
    """

    program_file = tmp_path / "demo.nanocode"
    program_file.write_text(program_src)

    result = subprocess.run(
        [sys.executable, "-m", "src.cli", str(program_file), "--scheduler", "lifo"],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["events"] >= 1


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
    assert summary["budget_exhausted"] is False


def test_cli_dry_run_validates_without_execution(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0))
      (rules
        (rule grow (pattern :sym seed) (action expand :fanout 2))
      )
      (max_steps 4)
    )
    """

    program_file = tmp_path / "demo.nanocode"
    program_file.write_text(program_src)

    result = subprocess.run(
        [sys.executable, "-m", "src.cli", str(program_file), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["dry_run"] is True
    assert summary["events"] == 0
    assert summary["rule_counts"] == {}
    assert summary["frontier"]  # root should be scheduled but not processed
    assert summary["budget_exhausted"] is False


def test_cli_can_emit_store_snapshot(tmp_path: Path):
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
    store_file = tmp_path / "store.json"

    result = subprocess.run(
        [sys.executable, "-m", "src.cli", str(program_file), "--store-json", str(store_file)],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    store_payload = json.loads(store_file.read_text())

    assert store_payload["root"] == summary["root"]
    assert any(record["children"] for record in store_payload["records"].values())
    assert store_payload["frontier"] == list(summary["frontier"])
    assert store_payload["processed"]


def test_cli_can_resume_from_store_snapshot(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0))
      (rules
        (rule grow (pattern :sym seed) (action expand :fanout 1))
        (rule normalize (pattern :sym F(seed)) (action reduce))
      )
      (max_steps 4)
    )
    """

    program_file = tmp_path / "demo.nanocode"
    program_file.write_text(program_src)
    store_file = tmp_path / "store.json"

    initial = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            str(program_file),
            "--store-json",
            str(store_file),
            "--steps-only",
            "--max-steps",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    initial_summary = json.loads(initial.stdout)
    stored_state = json.loads(store_file.read_text())

    assert stored_state["frontier"]
    assert initial_summary["events"] == 1
    assert initial_summary["budget_exhausted"] is True

    resumed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            str(program_file),
            "--load-store",
            str(store_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    resumed_summary = json.loads(resumed.stdout)
    assert resumed_summary["events"] >= initial_summary["events"]
    assert resumed_summary["frontier"] == []


def test_cli_restores_runtime_flags_from_store(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0 (child1) (child2)))
      (rules
        (rule mark (pattern) (action reduce))
      )
      (max_steps 2)
    )
    """

    program_file = tmp_path / "demo.nanocode"
    program_file.write_text(program_src)
    store_file = tmp_path / "store.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            str(program_file),
            "--walk-children",
            "--strict-matching",
            "--scheduler",
            "lifo",
            "--store-json",
            str(store_file),
            "--steps-only",
            "--max-steps",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stored_state = json.loads(store_file.read_text())
    assert stored_state["walk_children"] is True
    assert stored_state["strict_matching"] is True
    assert stored_state["scheduler"] == "lifo"

    resumed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            str(program_file),
            "--load-store",
            str(store_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(resumed.stdout)
    assert summary["walk_children"] is True
    assert summary["strict_matching"] is True
    assert summary["scheduler"] == "lifo"


def test_cli_enforces_rule_budgets_and_persists_them(tmp_path: Path):
    program_src = """
    (program demo
      (root (seed :scale 0 (seed :scale 0) (seed :scale 0)))
      (rules
        (rule grow (pattern :sym seed) (action expand :fanout 2))
      )
      (max_steps 6)
    )
    """

    program_file = tmp_path / "demo.nanocode"
    program_file.write_text(program_src)
    store_file = tmp_path / "store.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            str(program_file),
            "--walk-children",
            "--rule-budget",
            "grow=1",
            "--store-json",
            str(store_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(result.stdout)
    assert summary["rule_counts"] == {"grow": 1}
    assert summary["rule_budget_exhausted"] == ["grow"]
    assert summary["rule_budgets"] == {"grow": 1}

    stored_state = json.loads(store_file.read_text())
    assert stored_state["rule_budgets"] == {"grow": 1}
    assert stored_state["rule_budget_exhausted"] == ["grow"]

    resumed = subprocess.run(
        [sys.executable, "-m", "src.cli", str(program_file), "--load-store", str(store_file)],
        check=True,
        capture_output=True,
        text=True,
    )

    resumed_summary = json.loads(resumed.stdout)
    assert resumed_summary["rule_budgets"] == {"grow": 1}
    # No additional events should fire because the budget was already exhausted.
    assert resumed_summary["events"] == 0


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


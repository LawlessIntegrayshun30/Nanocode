## Nanocode prototype

This repository provides a lightweight Nanocode interpreter prototype built on a term-rewriting runtime.

### Running programs

```
python -m src.cli path/to/program.nanocode --trace-jsonl trace.jsonl
```

Programs are expressed as S-expressions; see `tests/test_cli.py` for end-to-end examples that emit a JSON summary and optional JSONL trace of runtime events.
You can also pipe program source directly via stdin using `-` as the program argument:

```
cat path/to/program.nanocode | python -m src.cli -
```

Pass `--walk-children` to automatically schedule child terms for rewriting instead of only rewriting the root/frontier returned by rules:

```
python -m src.cli path/to/program.nanocode --walk-children
```

Use `--strict-matching` to fail fast when multiple rules match the same term; without it, the first matching rule wins:

```
python -m src.cli path/to/program.nanocode --strict-matching
```

Validate a program (and optional stored snapshot) without executing any rewrites using `--dry-run` to catch issues quickly:

```
python -m src.cli path/to/program.nanocode --dry-run
```

Persist a JSON snapshot of the term store for replay or debugging with `--store-json`.
Snapshots now include the root term ID, the pending frontier, scheduler choice, and the set of already-processed terms so runs can be resumed:

```
python -m src.cli path/to/program.nanocode --store-json state/store.json
```

Resume from a stored snapshot (for example, after running with `--steps-only` to capture a mid-flight state) using `--load-store`:

```
python -m src.cli path/to/program.nanocode --load-store state/store.json
```

Switch the scheduler to depth-first style processing with LIFO semantics using `--scheduler lifo` (FIFO is the default):

```
python -m src.cli path/to/program.nanocode --scheduler lifo
```

Programs are validated before execution: rule names must be unique, scales cannot be negative, and step budgets must be positive. Invalid inputs surface as CLI errors so issues are caught early.

The CLI summary now includes per-rule and per-scale rewrite counts so you can track which rules fired and at what scale:

```
{
  "program": "demo",
  "root": "T0",
  "events": 2,
  "rule_counts": {"grow": 1, "normalize": 1},
  "scale_counts": {"0": 2},
  "idle": true,
  "budget_exhausted": false,
  "frontier": [],
  "store_size": 3
}
```

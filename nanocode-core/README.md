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

Semicolon-delimited comments are ignored by the parser, so you can annotate sources inline or on dedicated lines.

Pass `--walk-children` to automatically schedule child terms for rewriting instead of only rewriting the root/frontier returned by rules:

```
python -m src.cli path/to/program.nanocode --walk-children
```

When walking children, you can bound recursion with `--walk-depth N` to avoid traversing very deep trees:

```
python -m src.cli path/to/program.nanocode --walk-children --walk-depth 2
```

Use `--strict-matching` to fail fast when multiple rules match the same term; without it, the first matching rule wins:

```
python -m src.cli path/to/program.nanocode --strict-matching
```

Enable `--detect-conflicts` to refuse programs whose rules have deterministic overlapping patterns (same symbol and scale without predicates), providing a lightweight coherence guard before execution:

```
python -m src.cli path/to/program.nanocode --detect-conflicts
```

Enforce symbol arities and allowed scales by supplying a JSON signature via `--signature` so genomes stay well-formed during parsing and rewriting:

```
python -m src.cli path/to/program.nanocode --signature path/to/signature.json
```

Signature files declare per-symbol constraints:

```
{
  "symbols": {
    "root": {"min_children": 1, "max_children": 2, "scales": [0]},
    "leaf": {"min_children": 0, "max_children": 0, "scales": [1]}
  }
}
```

Validate a program (and optional stored snapshot) without executing any rewrites using `--dry-run` to catch issues quickly:

```
python -m src.cli path/to/program.nanocode --dry-run
```

Guard against runaway term growth by halting once the store exceeds a limit with `--max-terms`:

```
python -m src.cli path/to/program.nanocode --max-terms 1000
```

Persist a JSON snapshot of the term store for replay or debugging with `--store-json`.
Snapshots now include the root term ID, the pending frontier, scheduler choice/seed (for random runs), and the set of already-processed terms so runs can be resumed:

```
python -m src.cli path/to/program.nanocode --store-json state/store.json
```

Resume from a stored snapshot (for example, after running with `--steps-only` to capture a mid-flight state) using `--load-store`:

```
python -m src.cli path/to/program.nanocode --load-store state/store.json
```

Switch the scheduler to depth-first style processing with LIFO semantics using `--scheduler lifo` (FIFO is the default), or use
`--scheduler random` with `--scheduler-seed` to take a seeded randomized walk through the frontier:

```
python -m src.cli path/to/program.nanocode --scheduler lifo
python -m src.cli path/to/program.nanocode --scheduler random --scheduler-seed 7
```

When resuming from a snapshot, the runtime will honor the persisted scheduler, walk/strict flags, scheduler seed/state, and other metadata unless you explicitly override them (for example, with `--no-walk-children`).

Cap how many times a specific rule may fire with `--rule-budget name=N` (repeatable) to prevent runaway rewrites or enforce fairness:

```
python -m src.cli path/to/program.nanocode --walk-children --rule-budget grow=3 --rule-budget normalize=5
```

Rule budgets are stored in snapshots and surfaced in CLI summaries, along with a list of any exhausted budgets, so you can resume runs with the same limits.

Scope execution to a subset of rules with `--only-rule name` (repeatable) or skip specific rules with `--skip-rule name`; when both are provided, an error is raised if the sets overlap. Filters are validated against the program rule names, persisted in snapshots, honored on resume, and surfaced in CLI summaries:

```
python -m src.cli path/to/program.nanocode --only-rule grow --skip-rule normalize
```

Similarly, you can confine execution to certain term scales with `--only-scale N` (repeatable) or skip work on specific scales with `--skip-scale N`. Scale filters must be non-negative, are stored in snapshots, and are replayed on resume alongside other runtime configuration:

```
python -m src.cli path/to/program.nanocode --walk-children --only-scale 1
```

Programs are validated before execution: rule names must be unique, scales cannot be negative, and step budgets must be positive. Invalid inputs surface as CLI errors so issues are caught early.

The CLI summary now includes runtime configuration and per-rule/per-scale rewrite counts so you can track which rules fired and at what scale:

```
{
  "program": "demo",
  "root": "T0",
  "walk_children": false,
  "strict_matching": false,
  "detect_conflicts": false,
  "scheduler": "fifo",
  "scheduler_seed": null,
  "include_rules": null,
  "exclude_rules": [],
  "include_scales": null,
  "exclude_scales": [],
  "rule_budgets": {"grow": 3},
  "max_terms": 1000,
  "events": 2,
  "rule_counts": {"grow": 1, "normalize": 1},
  "scale_counts": {"0": 2},
  "rule_budget_exhausted": [],
  "term_limit_exhausted": false,
  "idle": true,
  "budget_exhausted": false,
  "frontier": [],
  "store_size": 3
}
```

### Prototype success script
Run the end-to-end prototype demo that builds micro/meso/macro structure from text, classifies it via a bridge, emits a JSONL trace, and saves a term-store snapshot in one command:

```
python -m src.prototype --text "nanocode" --trace-jsonl demo.trace.jsonl --store-json demo.store.json
```

The command constructs a deterministic program (micro tokens → meso motifs → lifted summary → macro bridge annotation), runs it with conflict detection and child walking enabled, and prints a JSON summary containing the final macro term and label alongside the optional trace/snapshot paths.

### Evolution scaffolding
- `src.evolution` provides deterministic mutation and recombination helpers over Nanocode genomes expressed as `Term` trees. You can mutate symbols/scales, delete or insert subtrees based on contextual spawn functions, and perform seeded crossovers between genomes to build evolutionary loops that stay within the Nanocode substrate.
- `measure_structure`/`validate_structure` expose deterministic size/depth/fanout/scale metrics and constraint checks so genomes can carry explicit well-formedness bounds during search.
- `evolve_population` and `evaluate_population` layer scoring, tournament selection, elitism, and callback-driven generation logging on top of those primitives so you can run reproducible evolutionary searches that keep provenance attached to each Nanocode genome and penalize invalid structures deterministically when constraints are supplied.

### Meta-level program representation
- `src.meta` converts rules/programs into Nanocode `Term` structures (`program_to_term`, `rule_to_term`) and back (`term_to_program`, `term_to_rule`). Actions now carry explicit names/params via `Action`, so rule sets and interpreter configurations can be serialized as first-class Nanocode data for self-hosting, analysis, or mutation in evolutionary loops.
- The conversion helpers validate shapes and preserve budgets/configuration (`max_steps`, `max_terms`), making it possible to treat entire interpreters as genomes without losing determinism or guardrails.

### Goal-directed agents and policy rollouts
- `src.agent` defines a minimal agent substrate pairing Nanocode programs with observation encoders and action decoders, plus a lightweight environment protocol. Policies are executed deterministically per observation by re-rooting the program and running through the interpreter.
- `rollout_agent` runs episodes against an environment, capturing per-step executions, accumulated reward, and optional goal-specific scores via user-provided reward functions. This makes it easy to score Nanocode genomes as agents for evolution or evaluation loops without leaving the symbolic substrate.
- Bridge schemas make agent/environment boundaries first-class: `BridgeSchema`/`BridgeBinding` describe typed input/output ports (with optional scales) and adapters that deterministically wrap observations/actions in tagged Nanocode terms. Bridge schemas serialize to/from terms (including deterministic metadata), keeping adapter capabilities representable for meta-level mutation alongside the rest of a genome.

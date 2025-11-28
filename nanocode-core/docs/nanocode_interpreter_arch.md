# Nanocode Interpreter Architecture (Draft)

## Goals
- Execute Nanocode programs as a term-rewriting system with explicit scales (micro/meso/macro) and guaranteed coherence properties (D_s(E_s(t^s)) = t^s).
- Provide a streaming runtime that can emit partial results (anytime property) and support deterministic replay for debugging.
- Offer extensible bridges to probabilistic/quantum backends without coupling core reduction semantics to hardware assumptions.

## High-level components
1. **Frontend**
   - A parser for a minimal Nanocode DSL (S-expressions first) that produces `Term` trees with scale annotations.
   - Validation layer to ensure rewrite rules are well-typed (e.g., fanout, allowed scale transitions) and to reject non-coherent rules at load time.
2. **Runtime kernel**
   - **Term store**: persistent, hash-addressed DAG of `Term` nodes to enable structural sharing and reversible steps.
   - **Rewrite engine**: orchestrates expansion/reduction; each step is logged with causal metadata for replay and visualization.
   - **Scheduler**: chooses rewrite order (depth-first, breadth-first, or heuristic) and supports cooperative interruption to expose anytime intermediate states.
3. **Bridges**
   - **Classical adapters**: micro/meso/macro hooks that map external streams into terms and export motifs back to clients.
   - **Quantum adapters**: pluggable samplers that turn shot counts into motifs and feed them into the meso layer; stays optional so the core remains deterministic.
4. **Developer tooling**
   - Tracing API to visualize scales and motifs over time.
   - Property checks for coherence and confluence on small bounded rewrites.

## Execution model
- **Term representation**: keep `Term(sym, scale, children)` from `src/terms.py`, but store children as stable IDs in the term store to allow deduplication and memoized reductions.
- **Rewrite rule shape**: `(pattern, action)` where `pattern` matches a `Term` (including scale) and `action` yields expanded or reduced terms.
- **Step semantics**:
  1. Load a program = set of rewrite rules + initial root term.
  2. Scheduler picks a frontier node; rewrite engine applies expansion or reduction.
  3. Each step emits an event `{before, after, scale, rule_id, timestamp}` to a log.
  4. Anytime snapshots are just prefixes of the log + term store.
- **Coherence enforcement**: during rule registration, run static checks that for every expansion rule `E_s`, a paired reduction `D_s` exists such that `D_s(E_s(t)) == t` for representative samples (property-based tests on random symbols).

## Proposed file/module layout
- `src/ast.py`: parser + AST/Term construction helpers from DSL.
- `src/term_store.py`: persistent DAG storage, hash-addressing, deduplication, snapshotting.
- `src/rewrite.py`: rule definitions, pattern matching, expansion/reduction helpers.
- `src/scheduler.py`: scheduling strategies and interruption hooks.
- `src/runtime.py`: orchestrates loading programs, executing steps, exposing streaming interface.
- `src/bridges/quantum.py`: wrappers around oracles/samplers → meso motifs; pure interface first, fake backend stays for tests.
- `src/bridges/classical.py`: micro/meso adapters for text/JSON streams → motifs.
- `src/tooling/trace.py`: event log emitters, replay, and visualization hooks.

## Near-term diffs to reach a runnable interpreter
1. **Refactor terms**: move `Term` to `term_store.py`, add stable IDs and hashing; adjust `expand/reduce` to work against the store rather than in-memory child lists.
2. **Introduce rewrite rules**: add `rewrite.py` with pattern/action definitions and unit tests covering coherence checks and simple confluence cases.
3. **Runtime skeleton**: implement `runtime.py` with a stepping API (`step()`, `run(max_steps)`, `snapshot()`), using the scheduler and emitting events.
4. **Parser**: create `ast.py` to parse a tiny DSL (S-expressions) into `Term` + rule objects, guarded by validation.
5. **Bridge isolation**: move existing `quantum_bridge.py` into `src/bridges/quantum.py` with a clear interface; add `classical.py` that wraps current micro/meso pipeline from `pipeline.py` as adapters.
6. **Observability**: add a tracing hook that writes step logs to disk/STDOUT; integrate with tests to assert emitted events.
7. **Tests**: expand `tests/` to cover coherence property, deterministic replay from logs, and scheduler heuristics (e.g., depth-first vs breadth-first outcomes).

## Prototype entry point (implemented)
- `Program`: declarative bundle of `root` term, rewrite `rules`, and a step budget.
- `Interpreter.run(program)`: builds a fresh `Runtime`, loads the root, and drives the scheduler until idle (or the step budget) while returning an execution snapshot (events, frontier, store records).
- `Event`: now captures the `before`/`after` term payloads to simplify tracing and replay scaffolding.

### Tracing hooks
- `JSONLTracer`: lightweight hook that can be passed into the runtime to stream `Event` records to any file-like sink for later replay/visualization.

### S-expression parser (prototype)
- `parse_program` in `src/ast.py` reads a minimal S-expression DSL:
  - `(root <term>)` builds a nested `Term` tree where `:scale N` overrides per-node scale and child lists follow the symbol.
  - `(rules (rule <name> (pattern :sym foo :scale 0) (action expand :fanout 2)) ...)` turns into `Rule` objects wired to built-in `expand`/`reduce` actions.
  - `(max_steps N)` controls the interpreter budget.
  - Semicolon-delimited comments are ignored so programs can be annotated inline without impacting parsing.
- Programs are validated before execution: duplicate rule names are rejected, negative scales are disallowed, and `max_steps` must be positive so malformed inputs fail fast.
- This parser feeds the existing `Interpreter` so end-to-end runs can be described textually and replayed via the runtime/tracer without hand-authoring Python rules.

### CLI entry point
- `python -m src.cli path/to/program.nanocode` parses an S-expression program, runs it through the runtime, and prints a JSON summary.
- `--dry-run` parses and validates a program (and optional stored snapshot) without executing rewrites to surface issues quickly.
- `--trace-jsonl` streams runtime events to a JSONL file for downstream replay/visualization.
- `--walk-children` instructs the runtime to automatically schedule child terms for rewriting (instead of only rewriting the frontiers returned by rules). Use `--walk-depth N` to cap recursion depth when walking children to avoid traversing very deep trees.
- `--strict-matching` raises on ambiguous rule matches rather than silently selecting the first rule, helping surface coherence issues early.
- `--scheduler lifo` switches the rewrite order to a LIFO/stack strategy (FIFO remains the default), useful for depth-first traversals.
- `--scheduler random` takes a seeded randomized walk through the frontier; pair with `--scheduler-seed` for reproducible runs. Random scheduler state (seed and RNG state) is persisted in snapshots so resuming preserves selection order.
- The CLI summary includes runtime configuration (scheduler, strict-matching, walk-children) plus per-rule and per-scale counters (`rule_counts`/`scale_counts`) alongside the frontier, store size, idle/budget exhaustion flags to highlight which rules fired, how much work remains, and whether a step budget halted execution.
- `--store-json` writes the term store snapshot to disk with root/frontier/processed metadata and runtime configuration so runs can be replayed or inspected offline without re-running the program. Pair with `--steps-only` to capture mid-flight snapshots.
- `--load-store` bootstraps the runtime from a stored snapshot, honoring the persisted scheduler/strict/walk settings (including stored walk-depth) by default (override with `--no-walk-children`, `--walk-depth`, or `--strict-matching/--no-strict-matching`).
- `--rule-budget name=N` (repeatable) caps how many times a rule may fire, preventing runaway rewrites; budgets are persisted in snapshots and surfaced in summaries alongside any exhausted budget list for visibility/resume fidelity.
- `--only-rule name` (repeatable) restricts execution to specific rules, while `--skip-rule name` excludes rules; filters are validated against the program, persisted in snapshots, and surfaced in summaries so resumed runs preserve the same rule visibility.
- `--only-scale N` (repeatable) confines work to terms at specific scales, while `--skip-scale N` excludes scales; filters must be non-negative, persist in snapshots, and are surfaced in summaries so resumed runs mirror the same scale visibility.
- `--max-terms N` halts rewriting once the store exceeds `N` unique terms, surfacing `term_limit_exhausted` in summaries/snapshots so pipelines can fail fast instead of allocating unbounded DAGs.

## Open questions to resolve during implementation
- What minimal DSL syntax is acceptable for v0? (Recommendation: S-expressions with `(expand ...)`/`(reduce ...)` forms.)
- Should confluence be enforced globally or verified on-demand per rule set? (Start with bounded checks in tests.)
- How should quantum motifs be represented so they remain compatible with classical motifs? (Propose `{amplitude_summary: ..., shots: ...}` schema shared across bridges.)
- What persistence format should the term store use for replay? (JSONL or SQLite; choose based on library policy.)

# Nanocode – Codex Task Spec

You are a software engineering agent working on the Nanocode substrate.

Context:
- Nanocode is a recursive, multi-scale term rewriting system.
- Mathematical definition and examples are in nanocode_report.md.

Your objectives:
1. Implement a multi-scale Nanocode interpreter.
2. Preserve the coherence condition:
     reduce(expand(t)) == t
3. Support at least three recursion levels (0,1,2,3).
4. Build tests that enforce:
     - coherence at all levels,
     - motif summarization stability,
     - error propagation analysis.

Initial engineering tasks:
- Improve src/terms.py to support child motifs and configurable motif summarization.
- Extend tests/test_terms.py using property-based tests.
- Implement a CLI entrypoint or REPL in src/ for running a full pipeline.

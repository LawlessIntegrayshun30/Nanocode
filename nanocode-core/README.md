## Nanocode prototype

This repository provides a lightweight Nanocode interpreter prototype built on a term-rewriting runtime.

### Running programs

```
python -m src.cli path/to/program.nanocode --trace-jsonl trace.jsonl
```

Programs are expressed as S-expressions; see `tests/test_cli.py` for an end-to-end example that emits a JSON summary and a JSONL trace of runtime events.

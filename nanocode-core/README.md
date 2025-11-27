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

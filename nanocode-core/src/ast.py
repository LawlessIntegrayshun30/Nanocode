from __future__ import annotations

import re
from typing import Iterable, Iterator, List, Sequence

from src.interpreter import Program, validate_program
from src.rewrite import Pattern, Rule
from src.terms import Term, expand, reduce


Token = str


def _symbol_from_expr(expr: object) -> str:
    if isinstance(expr, str):
        return expr
    if isinstance(expr, list) and expr:
        head, *tail = expr
        rendered_tail = ",".join(_symbol_from_expr(t) for t in tail)
        return f"{head}({rendered_tail})" if rendered_tail else str(head)
    raise ValueError(f"Invalid symbol expression: {expr}")


def _strip_comments(src: str) -> str:
    """Remove semicolon-to-EOL comments for a more forgiving DSL."""

    lines = []
    for line in src.splitlines():
        # Treat ';' as comment leader until end of line, mirroring Lisp-style
        # S-expression conventions.
        uncommented = line.split(";", 1)[0]
        lines.append(uncommented)
    return "\n".join(lines)


def _tokenize(src: str) -> List[Token]:
    cleaned = _strip_comments(src)
    return re.findall(r"\(|\)|[^\s()]+", cleaned)


def _read_tokens(tokens: Sequence[Token]) -> object:
    """Convert a flat token list into a nested S-expression list."""

    def read(queue: List[Token]) -> object:
        if not queue:
            return []

        tok = queue.pop(0)
        if tok == "(":
            items = []
            while queue and queue[0] != ")":
                items.append(read(queue))
            if not queue:  # pragma: no cover - defensive
                raise ValueError("Unbalanced parentheses in source")
            queue.pop(0)  # consume ')'
            return items

        if tok == ")":  # pragma: no cover - defensive
            raise ValueError("Unexpected ')'")

        return tok

    return read(list(tokens))


def parse_term(expr: object) -> Term:
    if isinstance(expr, str):
        return Term(sym=expr)

    if not isinstance(expr, list) or not expr:
        raise ValueError(f"Invalid term expression: {expr}")

    sym = expr[0]
    scale = 0
    children: List[object] = []

    it = iter(expr[1:])
    for item in it:
        if isinstance(item, str) and item == ":scale":
            try:
                scale_value = next(it)
            except StopIteration as exc:  # pragma: no cover - defensive
                raise ValueError("Missing :scale value") from exc
            scale = int(scale_value)
        else:
            children.append(item)

    return Term(sym=sym, scale=scale, children=[parse_term(child) for child in children])


def parse_pattern(expr: object) -> Pattern:
    if not isinstance(expr, list):
        raise ValueError("Pattern must be a list expression")

    items = expr[1:] if expr and expr[0] == "pattern" else expr
    sym = None
    scale = None

    i = 0
    while i < len(items):
        key = items[i]
        i += 1
        if not isinstance(key, str) or not key.startswith(":"):
            raise ValueError(f"Unexpected pattern token: {key}")

        values: List[object] = []
        while i < len(items) and not (isinstance(items[i], str) and items[i].startswith(":")):
            values.append(items[i])
            i += 1

        if not values:
            raise ValueError(f"Missing value for {key}")

        if key == ":sym":
            value = values[0] if len(values) == 1 else values
            sym = _symbol_from_expr(value)
        elif key == ":scale":
            scale = int(values[0])
        else:  # pragma: no cover - future extensions
            raise ValueError(f"Unknown pattern key: {key}")

    return Pattern(sym=sym, scale=scale)


def _action_expand(args: Iterable[Token]):
    fanout = 3
    it = iter(args)
    for key in it:
        if key == ":fanout":
            try:
                fanout = int(next(it))
            except StopIteration as exc:  # pragma: no cover - defensive
                raise ValueError("Missing :fanout value") from exc
    return lambda term, store: expand(term, fanout=fanout)


def _action_reduce(_: Iterable[Token]):
    return lambda term, store: reduce(term)


action_registry = {
    "expand": _action_expand,
    "reduce": _action_reduce,
}


def parse_action(expr: object):
    if not isinstance(expr, list) or not expr:
        raise ValueError("Action must be a list expression")

    items = expr[1:] if expr[0] == "action" else expr
    name, *args = items
    if name not in action_registry:
        raise ValueError(f"Unknown action: {name}")

    return action_registry[name](args)


def parse_rule(expr: object) -> Rule:
    if not isinstance(expr, list) or len(expr) < 4 or expr[0] != "rule":
        raise ValueError(f"Invalid rule expression: {expr}")

    _, name, pattern_expr, action_expr, *rest = expr
    if rest:
        raise ValueError(f"Unexpected tokens in rule {name}: {rest}")

    pattern = parse_pattern(pattern_expr)
    action = parse_action(action_expr)
    return Rule(name=name, pattern=pattern, action=action)


def parse_program(src: str) -> Program:
    expr = _read_tokens(_tokenize(src))
    if not isinstance(expr, list) or not expr or expr[0] != "program":
        raise ValueError("Program must start with (program ...)")

    name = expr[1] if len(expr) > 1 else "nanocode"
    root_term: Term | None = None
    rules: List[Rule] = []
    max_steps = 256
    max_terms: int | None = None

    for part in expr[2:]:
        if not isinstance(part, list) or not part:
            continue
        tag = part[0]
        if tag == "root":
            if len(part) != 2:
                raise ValueError("(root ...) expects a single term")
            root_term = parse_term(part[1])
        elif tag == "rules":
            for rule_expr in part[1:]:
                rules.append(parse_rule(rule_expr))
        elif tag == "max_steps":
            if len(part) != 2:
                raise ValueError("(max_steps N) expects a single integer")
            max_steps = int(part[1])
        elif tag == "max_terms":
            if len(part) != 2:
                raise ValueError("(max_terms N) expects a single integer")
            max_terms = int(part[1])

    if root_term is None:
        raise ValueError("Program missing root term")

    program = Program(name=name, root=root_term, rules=rules, max_steps=max_steps, max_terms=max_terms)
    validate_program(program)
    return program

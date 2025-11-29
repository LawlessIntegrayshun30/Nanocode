from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from src.terms import Term
from src.rewrite import Action


class InvalidBridgeSchema(ValueError):
    """Raised when a bridge schema violates deterministic constraints."""


@dataclass(frozen=True)
class BridgePort:
    name: str
    direction: Literal["in", "out"]
    scale: int | None = None
    description: str | None = None


@dataclass(frozen=True)
class BridgeSchema:
    name: str
    ports: tuple[BridgePort, ...]
    metadata: dict[str, object] | None = None

    def inputs(self) -> tuple[BridgePort, ...]:
        return tuple(p for p in self.ports if p.direction == "in")

    def outputs(self) -> tuple[BridgePort, ...]:
        return tuple(p for p in self.ports if p.direction == "out")

    def port(self, name: str) -> BridgePort:
        for port in self.ports:
            if port.name == name:
                return port
        raise KeyError(name)


def validate_bridge_schema(schema: BridgeSchema) -> BridgeSchema:
    seen: set[str] = set()
    for port in schema.ports:
        if port.name in seen:
            raise InvalidBridgeSchema(f"duplicate port name: {port.name}")
        seen.add(port.name)
        if port.direction not in {"in", "out"}:
            raise InvalidBridgeSchema(f"invalid direction for {port.name}: {port.direction}")
        if port.scale is not None and port.scale < 0:
            raise InvalidBridgeSchema(f"negative scale for {port.name}: {port.scale}")
    return schema


@dataclass(frozen=True)
class BridgeBinding:
    schema: BridgeSchema
    encode: dict[str, Callable[[object], Term]]
    decode: dict[str, Callable[[Term], object]]

    def encode_input(self, name: str, payload: object) -> Term:
        port = self.schema.port(name)
        if port.direction != "in":
            raise InvalidBridgeSchema(f"port {name} is not an input")
        try:
            encoder = self.encode[name]
        except KeyError as exc:
            raise InvalidBridgeSchema(f"missing encoder for port {name}") from exc
        term = encoder(payload)
        return _tag_port(port, term)

    def decode_output(self, name: str, term: Term) -> object:
        port = self.schema.port(name)
        if port.direction != "out":
            raise InvalidBridgeSchema(f"port {name} is not an output")
        try:
            decoder = self.decode[name]
        except KeyError as exc:
            raise InvalidBridgeSchema(f"missing decoder for port {name}") from exc
        _validate_port_tag(port, term)
        payload = _untag_port(term)
        return decoder(payload)


BRIDGE_SYM = "bridge"
PORT_SYM = "port"
METADATA_SYM = "metadata"


def bridge_schema_to_term(schema: BridgeSchema) -> Term:
    validate_bridge_schema(schema)
    ports = [
        Term(
            sym=f"{PORT_SYM}:{port.direction}:{port.name}",
            scale=port.scale or 0,
        )
        for port in schema.ports
    ]
    metadata_term = _metadata_to_term(schema.metadata)
    children = ports + ([metadata_term] if metadata_term is not None else [])
    return Term(sym=f"{BRIDGE_SYM}:{schema.name}", children=children)


def bridge_schema_from_term(term: Term) -> BridgeSchema:
    if not term.sym.startswith(f"{BRIDGE_SYM}:"):
        raise InvalidBridgeSchema(f"not a bridge term: {term.sym}")
    name = term.sym.split(":", 1)[1]
    ports: list[BridgePort] = []
    metadata: dict[str, object] | None = None
    for child in term.children:
        if not child.sym.startswith(f"{PORT_SYM}:"):
            if child.sym == METADATA_SYM:
                metadata = _metadata_from_term(child)
                continue
            raise InvalidBridgeSchema(f"not a port term: {child.sym}")
        _, direction, port_name = child.sym.split(":", 2)
        port = BridgePort(name=port_name, direction=direction, scale=child.scale)
        ports.append(port)
    schema = BridgeSchema(name=name, ports=tuple(ports), metadata=metadata)
    return validate_bridge_schema(schema)


def _tag_port(port: BridgePort, term: Term) -> Term:
    return Term(sym=f"{PORT_SYM}:{port.direction}:{port.name}", scale=term.scale, children=[term])


def _validate_port_tag(port: BridgePort, term: Term) -> None:
    expected = f"{PORT_SYM}:{port.direction}:{port.name}"
    if term.sym != expected:
        raise InvalidBridgeSchema(f"mismatched port tag: expected {expected}, got {term.sym}")


def _untag_port(term: Term) -> Term:
    if not term.children:
        raise InvalidBridgeSchema("port term missing payload child")
    return term.children[0]


def labeled_term(sym: str, payload: Term, *, scale: int | None = None) -> Term:
    """Attach a label sym to a payload term for bridge I/O annotation."""

    return Term(sym=sym, scale=scale if scale is not None else payload.scale, children=payload.children)


def _metadata_to_term(metadata: dict[str, object] | None) -> Term | None:
    if not metadata:
        return None
    return Term(
        sym=METADATA_SYM,
        children=[Term(sym=key, children=[_value_to_term(val)]) for key, val in sorted(metadata.items())],
    )


def _metadata_from_term(term: Term) -> dict[str, object]:
    if term.sym != METADATA_SYM:
        raise InvalidBridgeSchema(f"expected metadata term, got {term.sym}")
    metadata: dict[str, object] = {}
    for child in term.children:
        if not child.children:
            raise InvalidBridgeSchema("metadata entries must contain a value child")
        metadata[child.sym] = _value_from_term(child.children[0])
    return metadata


def _value_to_term(value: object) -> Term:
    if isinstance(value, bool):
        return Term(sym=str(value))
    if isinstance(value, int):
        return Term(sym=str(value))
    if isinstance(value, float):
        return Term(sym=str(value))
    if isinstance(value, str):
        return Term(sym=value)
    raise InvalidBridgeSchema(f"unsupported metadata type: {type(value)}")


def _value_from_term(term: Term) -> object:
    if term.children:
        raise InvalidBridgeSchema("metadata value terms must not have children")
    text = term.sym
    if text in {"True", "False"}:
        return text == "True"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def bridge_call_action(
    binding: BridgeBinding,
    output_port: str,
    fn: Callable[[Term], object],
) -> Action:
    """Create a rewrite Action that consults a bridge and annotates the term.

    The callable ``fn`` acts as the deterministic oracle producing payloads for
    the named ``output_port``. The resulting term keeps the original payload as
    a child alongside the port-tagged bridge output so downstream rules can
    consume the external signal without breaking determinism.
    """

    port = binding.schema.port(output_port)
    if port.direction != "out":
        raise InvalidBridgeSchema(f"Port {output_port} is not an output")
    try:
        encoder = binding.encode[output_port]
    except KeyError as exc:
        raise InvalidBridgeSchema(f"missing encoder for output port {output_port}") from exc

    def _apply(term: Term, _store) -> Term:
        payload = fn(term)
        encoded = encoder(payload)
        tagged = _tag_port(port, encoded)
        return Term(sym=f"bridge:{term.sym}", scale=max(term.scale, port.scale or term.scale), children=[term, tagged])

    return Action(name=f"bridge:{binding.schema.name}:{output_port}", params={}, fn=_apply)

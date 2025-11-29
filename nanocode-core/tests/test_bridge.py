from __future__ import annotations

import pytest

from src.bridge import (
    BRIDGE_SYM,
    METADATA_SYM,
    PORT_SYM,
    BridgeBinding,
    BridgePort,
    BridgeSchema,
    InvalidBridgeSchema,
    bridge_call_action,
    bridge_schema_from_term,
    bridge_schema_to_term,
    validate_bridge_schema,
)
from src.terms import Term


def test_validate_bridge_schema_rejects_duplicates_and_negatives():
    schema = BridgeSchema(
        name="demo",
        ports=(
            BridgePort(name="obs", direction="in", scale=0),
            BridgePort(name="obs", direction="out", scale=1),
        ),
    )
    with pytest.raises(InvalidBridgeSchema):
        validate_bridge_schema(schema)

    schema = BridgeSchema(name="demo", ports=(BridgePort(name="obs", direction="in", scale=-1),))
    with pytest.raises(InvalidBridgeSchema):
        validate_bridge_schema(schema)


def test_bridge_schema_term_round_trip():
    schema = BridgeSchema(
        name="adapter",
        ports=(
            BridgePort(name="obs", direction="in", scale=0),
            BridgePort(name="act", direction="out", scale=1),
        ),
        metadata={"version": 1, "train": False, "note": "demo"},
    )

    as_term = bridge_schema_to_term(schema)
    assert as_term.sym == f"{BRIDGE_SYM}:{schema.name}"
    assert {child.sym for child in as_term.children} == {
        f"{PORT_SYM}:in:obs",
        f"{PORT_SYM}:out:act",
        "metadata",
    }

    restored = bridge_schema_from_term(as_term)
    assert restored == schema


def test_bridge_binding_encode_decode():
    schema = BridgeSchema(
        name="adapter",
        ports=(
            BridgePort(name="obs", direction="in", scale=0),
            BridgePort(name="act", direction="out", scale=0),
        ),
    )
    binding = BridgeBinding(
        schema=schema,
        encode={"obs": lambda payload: Term(sym=str(payload), scale=0)},
        decode={"act": lambda term: term.sym},
    )

    encoded = binding.encode_input("obs", 3)
    assert encoded.sym == f"{PORT_SYM}:in:obs"
    assert encoded.children[0].sym == "3"

    with pytest.raises(InvalidBridgeSchema):
        binding.encode_input("act", 3)

    action_term = Term(sym=f"{PORT_SYM}:out:act", scale=0, children=[Term(sym="fire", scale=0)])
    decoded = binding.decode_output("act", action_term)
    assert decoded == "fire"

    with pytest.raises(InvalidBridgeSchema):
        binding.decode_output("obs", action_term)

    mismatched = Term(sym=f"{PORT_SYM}:out:wrong", scale=0, children=[Term(sym="fire", scale=0)])
    with pytest.raises(InvalidBridgeSchema):
        binding.decode_output("act", mismatched)


def test_bridge_schema_rejects_unsupported_metadata_types():
    schema = BridgeSchema(
        name="adapter",
        ports=(BridgePort(name="obs", direction="in", scale=0),),
        metadata={"unsupported": object()},
    )

    with pytest.raises(InvalidBridgeSchema):
        bridge_schema_to_term(schema)


def test_bridge_call_action_enriches_term():
    schema = BridgeSchema(
        name="oracle",
        ports=(BridgePort(name="score", direction="out", scale=1),),
    )
    binding = BridgeBinding(
        schema=schema,
        encode={"score": lambda payload: Term(sym=str(payload), scale=1)},
        decode={"score": lambda term: float(term.sym)},
    )

    def scorer(term: Term) -> float:
        return float(len(term.sym))

    action = bridge_call_action(binding, "score", scorer)
    base = Term(sym="seed", scale=0)
    enriched = action(base, None)
    assert enriched.sym.startswith("bridge:")
    assert enriched.children[1].sym.startswith(f"{PORT_SYM}:out:score")
    assert enriched.children[1].children[0].sym == "4.0"

import pytest

from src.rewrite import Pattern, Rule
from src.runtime import Runtime
from src.signature import Signature, SignatureError
from src.terms import Term


def test_signature_validates_tree():
    signature = Signature.from_dict(
        {
            "symbols": {
                "root": {"min_children": 1, "max_children": 2, "scales": [0]},
                "leaf": {"min_children": 0, "max_children": 0, "scales": [1]},
            }
        }
    )

    signature.validate_tree(Term(sym="root", scale=0, children=[Term(sym="leaf", scale=1)]))


def test_signature_enforced_in_runtime():
    signature = Signature.from_dict(
        {
            "symbols": {
                "root": {"min_children": 1, "max_children": 1, "scales": [0]},
                "leaf": {"min_children": 0, "max_children": 0, "scales": [1]},
            }
        }
    )

    def explode(term, store):
        return Term(sym="leaf", scale=1, children=[Term(sym="leaf", scale=1)])

    runtime = Runtime(
        [Rule(name="expand", pattern=Pattern(sym="leaf", scale=1), action=explode)],
        signature=signature,
        walk_children=True,
    )

    runtime.load(Term(sym="root", scale=0, children=[Term(sym="leaf", scale=1)]))

    with pytest.raises(SignatureError):
        runtime.run_until_idle()

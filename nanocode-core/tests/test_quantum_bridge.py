import random

from src.quantum_bridge import classical_decision, motif_counts, quantum_to_classical, sample_oracle


def test_motif_counts_and_decision():
    samples = ["000", "111", "000", "101"]
    counts = motif_counts(samples)
    assert counts["000"] == 2
    assert classical_decision(counts) in counts


def test_quantum_to_classical_is_deterministic_with_seed():
    random.seed(123)
    result = quantum_to_classical(n=10)
    assert isinstance(result, str)


def test_sample_oracle_respects_n_argument():
    samples = sample_oracle(lambda: "abc", n=3)
    assert samples == ["abc", "abc", "abc"]

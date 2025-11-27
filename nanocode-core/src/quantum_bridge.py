import random
from typing import Callable, List, Dict

def fake_quantum_oracle() -> str:
    outcomes = {"000": 0.4, "111": 0.3, "101": 0.2, "010": 0.1}
    r = random.random()
    cumulative = 0
    for bits, p in outcomes.items():
        cumulative += p
        if r <= cumulative:
            return bits
    return "000"

def sample_oracle(fn: Callable[[], str], n=100) -> List[str]:
    return [fn() for _ in range(n)]

def motif_counts(samples: List[str]) -> Dict[str, int]:
    counts = {}
    for s in samples:
        counts[s] = counts.get(s, 0) + 1
    return counts

def classical_decision(counts: Dict[str, int]) -> str:
    if not counts:
        return "empty"
    return max(counts.items(), key=lambda kv: kv[1])[0]

def quantum_to_classical(n=50) -> str:
    samples = sample_oracle(fake_quantum_oracle, n)
    motifs = motif_counts(samples)
    return classical_decision(motifs)

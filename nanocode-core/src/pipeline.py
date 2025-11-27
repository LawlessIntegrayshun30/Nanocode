from typing import List, Dict, Any

def micro_layer(data: str) -> List[str]:
    return list(data)

def meso_layer(tokens: List[str]) -> Dict[str, Any]:
    motifs = {}
    for i in range(len(tokens) - 1):
        bg = tokens[i] + tokens[i+1]
        motifs[bg] = motifs.get(bg, 0) + 1
    return {"bigrams": motifs}

def macro_layer(motifs: Dict[str, Any]) -> str:
    bigrams = motifs.get("bigrams", {})
    if not bigrams:
        return "empty"
    dominant = max(bigrams.items(), key=lambda kv: kv[1])[0]
    return f"dominant={dominant}"

def run_pipeline(raw: str) -> str:
    atoms = micro_layer(raw)
    motifs = meso_layer(atoms)
    return macro_layer(motifs)

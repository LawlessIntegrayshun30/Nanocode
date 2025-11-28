from src.pipeline import macro_layer, meso_layer, micro_layer, run_pipeline


def test_micro_to_macro_pipeline():
    atoms = micro_layer("abba")
    assert atoms == ["a", "b", "b", "a"]

    motifs = meso_layer(atoms)
    assert motifs["bigrams"]["ab"] == 1
    assert motifs["bigrams"]["bb"] == 1

    macro = macro_layer(motifs)
    assert macro.startswith("dominant=")

    end_to_end = run_pipeline("abba")
    assert end_to_end.startswith("dominant=")

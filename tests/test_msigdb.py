"""MSigDB loader: mechanical mapping rules on synthetic data, key facts on the real snapshot."""
import pytest

from lab import chembl, msigdb

SYMBOLS = {"MTOR": {"P42345"}, "FKBP1A": {"P62942"}, "HTT": {"P31645", "P42858"}}


def _gmt(tmp_path, lines):
    p = tmp_path / "c2.cp.v4.0.symbols.gmt"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_unique_symbols_map_ambiguous_and_unknown_are_counted_not_guessed(tmp_path):
    p = _gmt(tmp_path, ["SET_A\thttp://x\tmtor\tFKBP1A\tHTT\tNOPE1\tNOPE2"])
    sets, report = msigdb.load_gene_sets(SYMBOLS, path=p)
    assert sets == {"SET_A": {"P42345", "P62942"}}            # case-insensitive, HTT not guessed
    assert report == [{"set_name": "SET_A", "n_symbols": 5, "n_mapped": 2,
                       "n_ambiguous": 1, "n_unmapped": 2}]


def test_set_with_no_mapped_gene_is_reported_but_not_returned(tmp_path):
    p = _gmt(tmp_path, ["EMPTY\tx\tNOPE", "FULL\tx\tMTOR"])
    sets, report = msigdb.load_gene_sets(SYMBOLS, path=p)
    assert list(sets) == ["FULL"]
    assert [r["set_name"] for r in report] == ["EMPTY", "FULL"]


def test_find_gmt_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        msigdb.find_gmt("c2.cp", tmp_path)


def test_symbol_map_trims_uppercases_and_skips_null_symbols():
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE component_sequences (component_id INT, accession TEXT, organism TEXT);
        CREATE TABLE component_synonyms (component_id INT, component_synonym TEXT, syn_type TEXT);
        INSERT INTO component_sequences VALUES (1,'P62942','Homo sapiens'),(2,'Q00001','Mus musculus'),
                                               (3,'Q00003','Homo sapiens');
        INSERT INTO component_synonyms VALUES (1,'FKBP1 ','GENE_SYMBOL'),(1,'Fkbp1a','GENE_SYMBOL'),
            (1,'FKBP-12','UNIPROT'),(2,'MOUSEGENE','GENE_SYMBOL'),(3,NULL,'GENE_SYMBOL'),
            (3,'  ','GENE_SYMBOL');""")
    assert chembl.symbol_map(c) == {"FKBP1": {"P62942"}, "FKBP1A": {"P62942"}}


@pytest.mark.skipif(not (chembl.DB_PATH.exists() and any(msigdb.MSIGDB_DIR.rglob("c2.cp.v4.0.symbols.gmt"))),
                    reason="ChEMBL 19 or MSigDB v4.0 not downloaded")
def test_real_snapshot_mtor_sets():
    sets, report = msigdb.load_from_snapshot("c2.cp")
    assert {"P62942", "P42345"} <= sets["BIOCARTA_MTOR_PATHWAY"]      # FKBP1A and MTOR
    assert "P62942" not in sets["KEGG_MTOR_SIGNALING_PATHWAY"]        # the gap the decision record names
    assert len(report) >= len(sets) > 0

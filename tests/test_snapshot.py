"""Snapshot: determinism, tamper detection, cutoff guard and no leaked names; real data if present."""
import json

import pytest
from test_chembl import _act, _db

from lab import chembl, msigdb, snapshot

GMT = "SET_A\thttp://x\tMTOR\tFKBP1A\tNOPE\nSET_B\thttp://x\tIL6\n"


def _conn():
    c = _db()
    c.executescript("""
        CREATE TABLE component_synonyms (component_id INT, component_synonym TEXT, syn_type TEXT);
        UPDATE component_sequences SET accession = accession;
        ALTER TABLE component_sequences ADD COLUMN organism TEXT;
        UPDATE component_sequences SET organism = 'Homo sapiens';
        INSERT INTO component_synonyms VALUES (100,'MTOR','GENE_SYMBOL'),(101,'FKBP1A','GENE_SYMBOL');""")
    c.execute("INSERT INTO drug_mechanism VALUES (1, 11)")
    _act(c, 1, 10, 2010)
    return c


def _gmt_root(tmp_path):
    root = tmp_path / "gmt"
    root.mkdir(parents=True, exist_ok=True)
    for col in snapshot.COLLECTIONS:
        (root / f"{col}.v4.0.symbols.gmt").write_text(GMT)
    return root


def _build(tmp_path, name):
    return snapshot.build(2015, tmp_path / name, _conn(), gmt_root=_gmt_root(tmp_path))


def test_same_inputs_give_identical_bytes(tmp_path):
    a, b = _build(tmp_path, "a"), _build(tmp_path, "b")
    assert sorted(p.name for p in a.iterdir()) == sorted(p.name for p in b.iterdir())
    for p in a.iterdir():
        assert p.read_bytes() == (b / p.name).read_bytes()


def test_load_roundtrip_in_the_shape_scoring_uses(tmp_path):
    _build(tmp_path, "s")
    snap = snapshot.load(2015, tmp_path / "s")
    assert snap.drugs == ["CHEMBL1"]  # CHEMBL4 has no human target: outside the pool
    assert snap.links["curated"] == [("CHEMBL1", "P62942")]
    assert snap.links["curated+activity"] == [("CHEMBL1", "P42345"), ("CHEMBL1", "P62942")]
    assert snap.gene_sets["c2.cp"]["SET_A"] == {"P42345", "P62942"}
    assert "SET_B" not in snap.gene_sets["c2.cp"]                 # IL6 unknown to this ChEMBL
    assert snap.pool() == [{"drug_id": "CHEMBL1", "targets": ["P62942"]}]
    assert snap.pool("curated+activity") == [{"drug_id": "CHEMBL1", "targets": ["P42345", "P62942"]}]
    assert snap.manifest["counts"]["drugs"] == 1
    assert snap.manifest["rules"]["pool"].startswith(chembl.POOL_DEFINITION)


def test_any_edit_is_refused(tmp_path):
    folder = _build(tmp_path, "s")
    (folder / "drug_pool.json").write_text("[]\n")
    with pytest.raises(ValueError, match="corrupt"):
        snapshot.load(2015, tmp_path / "s")
    folder = _build(tmp_path, "t")                      # a fresh, valid snapshot
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["files"]["drug_pool.json"] = "0" * 64      # edit the manifest instead of the file
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="corrupt|edited"):
        snapshot.load(2015, tmp_path / "t")


def test_cutoff_before_chembl_19_is_refused(tmp_path):
    with pytest.raises(ValueError, match="leak"):
        snapshot.build(2014, tmp_path, _conn(), gmt_root=_gmt_root(tmp_path))


def test_snapshot_holds_no_drug_names(tmp_path):
    folder = _build(tmp_path, "s")
    text = "".join(p.read_text() for p in folder.iterdir())
    assert "drugA" not in text and "pref_name" not in text


@pytest.mark.skipif(not (chembl.DB_PATH.exists() and any(msigdb.MSIGDB_DIR.rglob("c2.all.v4.0.symbols.gmt"))),
                    reason="ChEMBL 19 or MSigDB v4.0 not downloaded")
def test_real_snapshot_numbers_and_determinism(tmp_path):
    a = snapshot.build(2015, tmp_path / "a")
    b = snapshot.build(2015, tmp_path / "b")
    assert snapshot.load(2015, tmp_path / "a").sha256 == snapshot.load(2015, tmp_path / "b").sha256
    snap = snapshot.load(2015, tmp_path / "a")
    # pool = data/README.md's definition; curated+activity links are kept for pool drugs only
    assert (len(snap.drugs), len(snap.links["curated"]), len(snap.links["curated+activity"])) == (1146, 3779, 5516)
    assert {"P62942", "P42345"} <= snap.gene_sets["c2.cp"]["BIOCARTA_MTOR_PATHWAY"]
    assert sum(len(p.read_bytes()) for p in a.iterdir()) == sum(len(p.read_bytes()) for p in b.iterdir())

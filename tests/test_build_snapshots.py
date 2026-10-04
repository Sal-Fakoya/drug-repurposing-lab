"""scripts/build_snapshots.py on a tiny fixture ChEMBL database and GMT; real data if present."""
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from test_chembl import _act
from test_snapshot import _conn

from lab import chembl

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_snapshots",
                                               ROOT / "scripts" / "build_snapshots.py")
bs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bs)

# SET_A has an ambiguous alias (SHARED) and an unknown symbol; SET_B has IL6 (no ChEMBL target).
GMT = "SET_A\thttp://x\tMTOR\tFKBP1A\tSHARED\tNOPE\nSET_B\thttp://x\tIL6\tMTOR\n"


def _fixture_conn() -> sqlite3.Connection:
    """test_snapshot's fixture: CHEMBL1 (salt CHEMBL2) -> FKBP1A curated, MTOR by activity."""
    c = _conn()
    c.execute("UPDATE molecule_dictionary SET pref_name = 'sirolimus' WHERE molregno = 1")
    c.executemany("INSERT INTO component_synonyms VALUES (?, ?, 'GENE_SYMBOL')",
                  [(103, "SHARED"), (104, "SHARED")])  # one alias, two proteins: ambiguous
    _act(c, 4, 10, 2012)  # CHEMBL4 (approved) reaches mTOR by activity only: not in the pool
    return c


def _gmt_root(tmp_path: Path) -> Path:
    root = tmp_path / "msigdb"
    root.mkdir(exist_ok=True)
    for col in ("c2.cp", "c2.all"):
        (root / f"{col}.v4.0.symbols.gmt").write_text(GMT)
    return root


@pytest.fixture
def built(tmp_path):
    conn = _fixture_conn()
    out = tmp_path / "snapshots" / "v1"
    manifest = bs.build(conn, _gmt_root(tmp_path), out)
    return conn, out, manifest


def test_writes_three_parquet_tables_and_a_manifest(built):
    _, out, manifest = built
    assert sorted(p.name for p in out.iterdir()) == [
        "drug_pool.parquet", "drug_targets.parquet", "gene_sets.parquet", "manifest.json"]
    assert json.loads((out / "manifest.json").read_text()) == manifest
    for name, entry in manifest["tables"].items():
        data = (out / entry["file"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["rows"] == len(pd.read_parquet(out / entry["file"]))
    assert manifest["cutoff_year"] == 2015
    assert manifest["sources"]["chembl"]["release"] == "ChEMBL_19"
    assert manifest["sources"]["msigdb"]["release"].startswith("4.0")
    assert set(manifest["sources"]["msigdb"]["gmt_sha256"]) == {
        "c2.cp.v4.0.symbols.gmt", "c2.all.v4.0.symbols.gmt"}


def test_drug_targets_are_parent_human_accessions_with_symbols_per_definition(built):
    _, out, _ = built
    t = pd.read_parquet(out / "drug_targets.parquet")
    rows = set(map(tuple, t[["definition", "drug_chembl_id", "uniprot_accession",
                             "gene_symbol"]].itertuples(index=False)))
    assert rows == {("curated", "CHEMBL1", "P62942", "FKBP1A"),
                    ("curated+activity", "CHEMBL1", "P62942", "FKBP1A"),
                    ("curated+activity", "CHEMBL1", "P42345", "MTOR")}  # mTOR only by activity
    assert "CHEMBL2" not in set(t["drug_chembl_id"])  # the salt is merged into its parent
    assert "CHEMBL4" not in set(t["drug_chembl_id"])  # activity-only drug: outside the pool


def test_drug_pool_is_approved_parents_with_a_human_target(built):
    _, out, manifest = built
    pool = pd.read_parquet(out / "drug_pool.parquet")
    assert pool.to_dict("records") == [
        {"drug_chembl_id": "CHEMBL1", "n_targets_curated": 1, "n_targets_curated_activity": 2}]
    # CHEMBL4 is approved but has only an activity link; CHEMBL3 is not approved
    assert manifest["pool"] == {"size": 1, "definition": chembl.POOL_DEFINITION}


def test_gene_sets_keep_every_symbol_and_label_the_mapping(built):
    _, out, _ = built
    g = pd.read_parquet(out / "gene_sets.parquet")
    a = g[(g["collection"] == "c2.cp") & (g["set_name"] == "SET_A")].set_index("gene_symbol")
    assert a.loc["MTOR", "uniprot_accession"] == "P42345" and a.loc["MTOR", "mapping"] == "mapped"
    assert a.loc["FKBP1A", "uniprot_accession"] == "P62942"
    assert a.loc["SHARED", "mapping"] == "ambiguous" and pd.isna(a.loc["SHARED", "uniprot_accession"])
    assert a.loc["NOPE", "mapping"] == "unmapped"
    assert set(g["collection"]) == {"c2.cp", "c2.all"} and len(g) == 2 * 6


def test_same_inputs_give_identical_files(tmp_path):
    a = bs.build(_fixture_conn(), _gmt_root(tmp_path), tmp_path / "a")
    b = bs.build(_fixture_conn(), _gmt_root(tmp_path), tmp_path / "b")
    assert a["tables"] == b["tables"]


def test_tables_hold_no_drug_names(built):
    _, out, _ = built
    for p in out.glob("*.parquet"):
        assert "sirolimus" not in pd.read_parquet(p).to_csv().lower()


def test_report_prints_pool_drug_targets_and_gene_sets(built):
    conn, out, _ = built
    text = bs.report(conn, out, drugs=["sirolimus", "tocilizumab"], genes=["MTOR", "IL6"])
    assert f"Pool size: 1 drugs ({chembl.POOL_DEFINITION})" in text
    assert "sirolimus (CHEMBL1):" in text
    assert "curated           FKBP1A (P62942)" in text
    assert "MTOR (P42345)" in text and "tocilizumab: not in ChEMBL" in text
    assert "c2.cp sets containing MTOR (2): SET_A, SET_B" in text
    assert "c2.cp sets containing IL6 (1): SET_B" in text


def test_cli_finds_the_database_and_writes_the_default_layout(tmp_path, capsys):
    db = tmp_path / "raw" / "chembl19" / "chembl_19_sqlite" / "chembl_19.db"
    db.parent.mkdir(parents=True)
    source, disk = _fixture_conn(), sqlite3.connect(db)
    source.commit()  # backup() retries forever while the source has an open write transaction
    source.backup(disk)
    disk.close()
    assert bs.find_chembl_db(tmp_path / "raw" / "chembl19") == db
    out = tmp_path / "snapshots" / "v1"
    bs.main(["--chembl-db", str(db), "--msigdb", str(_gmt_root(tmp_path)), "--out", str(out),
             "--drugs", "sirolimus"])
    printed = capsys.readouterr().out
    assert "Pool size" in printed and "sirolimus (CHEMBL1)" in printed and "wrote" in printed


def test_refuses_a_cutoff_before_chembl_19_and_a_missing_database(tmp_path):
    with pytest.raises(ValueError, match="before ChEMBL 19"):
        bs.build(_fixture_conn(), _gmt_root(tmp_path), tmp_path / "x", cutoff_year=2014)
    with pytest.raises(FileNotFoundError, match="setup_data.py"):
        bs.find_chembl_db(tmp_path / "nowhere")


def test_snapshots_folder_is_gitignored():
    assert "data/snapshots/" in (ROOT / ".gitignore").read_text().splitlines()


@pytest.mark.skipif(not chembl.DB_PATH.exists(), reason="ChEMBL 19 snapshot not downloaded")
def test_real_snapshot(tmp_path):
    conn = chembl.connect()
    manifest = bs.build(conn, bs.msigdb.MSIGDB_DIR, tmp_path / "v1")
    assert manifest["pool"]["size"] == 1146  # data/README.md, docs/cutoff-decision.md
    assert len(pd.read_parquet(tmp_path / "v1" / "drug_pool.parquet")) == 1146
    t = pd.read_parquet(tmp_path / "v1" / "drug_targets.parquet")
    sirolimus = conn.execute("SELECT chembl_id FROM molecule_dictionary "
                             "WHERE lower(pref_name) = 'sirolimus'").fetchone()[0]
    mine = t[t["drug_chembl_id"] == sirolimus]
    assert set(mine.loc[mine["definition"] == "curated", "uniprot_accession"]) == {"P62942"}
    assert "P42345" in set(mine.loc[mine["definition"] == "curated+activity", "uniprot_accession"])

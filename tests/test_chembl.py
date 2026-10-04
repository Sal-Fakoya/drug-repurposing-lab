"""ChEMBL loader: synthetic database for the rules, the real snapshot (if present) for the facts."""
import sqlite3

import pytest

from lab import chembl

SCHEMA = """
CREATE TABLE version (name TEXT, creation_date TEXT, comments TEXT);
CREATE TABLE molecule_dictionary (molregno INT, chembl_id TEXT, pref_name TEXT, max_phase INT);
CREATE TABLE molecule_hierarchy (molregno INT, parent_molregno INT, active_molregno INT);
CREATE TABLE drug_mechanism (molregno INT, tid INT);
CREATE TABLE target_dictionary (tid INT, pref_name TEXT, organism TEXT, chembl_id TEXT);
CREATE TABLE target_components (tid INT, component_id INT);
CREATE TABLE component_sequences (component_id INT, accession TEXT);
CREATE TABLE assays (assay_id INT, tid INT);
CREATE TABLE docs (doc_id INT, year INT);
CREATE TABLE activities (assay_id INT, doc_id INT, molregno INT, standard_type TEXT,
    standard_units TEXT, standard_value REAL, standard_relation TEXT);
"""


def _db(version="ChEMBL_19"):
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    c.execute("INSERT INTO version VALUES (?, '2014-07-03', '')", (version,))
    # molecules: 1 sirolimus (approved, own parent), 2 its salt (approved, parent 1),
    # 3 experimental (phase 2), 4 approved, no hierarchy row
    c.executemany("INSERT INTO molecule_dictionary VALUES (?,?,?,?)",
                  [(1, "CHEMBL1", "drugA", 4), (2, "CHEMBL2", "drugA salt", 4),
                   (3, "CHEMBL3", "experimental", 2), (4, "CHEMBL4", "drugD", 4)])
    c.executemany("INSERT INTO molecule_hierarchy VALUES (?,?,?)", [(1, 1, 1), (2, 1, 1), (3, 3, 3)])
    # target 10 is mTOR but its NAME says FKBP12 (the real ChEMBL 19 mislabel); 11 is FKBP1A;
    # 12 is a rat protein; 13 is a complex of two human proteins.
    c.executemany("INSERT INTO target_dictionary VALUES (?,?,?,?)",
                  [(10, "FK506 binding protein 12", "Homo sapiens", "CHEMBL2842"),
                   (11, "FK506-binding protein 1A", "Homo sapiens", "CHEMBL1"),
                   (12, "rat thing", "Rattus norvegicus", "CHEMBL3"),
                   (13, "complex", "Homo sapiens", "CHEMBL4")])
    c.executemany("INSERT INTO component_sequences VALUES (?,?)",
                  [(100, "P42345"), (101, "P62942"), (102, "Q00001"), (103, "Q00002"),
                   (104, "Q00003")])
    c.executemany("INSERT INTO target_components VALUES (?,?)",
                  [(10, 100), (11, 101), (12, 102), (13, 103), (13, 104)])
    return c


def _act(c, molregno, tid, year, value=10.0, rel="=", units="nM", kind="IC50"):
    n = c.execute("SELECT COUNT(*) FROM activities").fetchone()[0] + 1
    c.execute("INSERT INTO assays VALUES (?,?)", (n, tid))
    c.execute("INSERT INTO docs VALUES (?,?)", (n, year))
    c.execute("INSERT INTO activities VALUES (?,?,?,?,?,?,?)", (n, n, molregno, kind, units, value, rel))


def test_pool_collapses_salts_and_drops_unapproved():
    assert chembl.approved_parents(_db()) == ["CHEMBL1", "CHEMBL4"]


def test_curated_matches_by_accession_through_the_salt_to_its_parent():
    c = _db()
    c.execute("INSERT INTO drug_mechanism VALUES (2, 11)")  # on the salt form
    c.execute("INSERT INTO drug_mechanism VALUES (1, 12)")  # non-human, dropped
    c.execute("INSERT INTO drug_mechanism VALUES (3, 11)")  # not approved, dropped
    assert chembl.drug_target_links(c, "curated") == [("CHEMBL1", "P62942")]


def test_complex_target_links_every_human_component():
    c = _db()
    c.execute("INSERT INTO drug_mechanism VALUES (4, 13)")
    assert chembl.drug_target_links(c, "curated") == [("CHEMBL4", "Q00002"), ("CHEMBL4", "Q00003")]


def test_mislabelled_mtor_target_is_reached_by_accession_not_name():
    c = _db()
    _act(c, 1, 10, 2010)  # target CHEMBL2842, named FKBP12, accession P42345
    assert chembl.drug_target_links(c, "curated") == []
    assert chembl.drug_target_links(c, "curated+activity", 2015) == [("CHEMBL1", "P42345")]


def test_activity_rules_cutoff_relation_value_units_type():
    c = _db()
    _act(c, 1, 10, 2014)                     # kept
    _act(c, 1, 11, 2015)                     # document at the cutoff year: dropped
    _act(c, 1, 11, None)                     # undated document: dropped
    _act(c, 4, 10, 2010, rel=">")            # '>' does not show <= 1000: dropped
    _act(c, 4, 10, 2010, rel=None)           # no relation: dropped
    _act(c, 4, 10, 2010, value=1001)         # above threshold: dropped
    _act(c, 4, 10, 2010, units="uM")         # not nM: dropped
    _act(c, 4, 10, 2010, kind="EC50")        # not IC50/Ki/Kd: dropped
    _act(c, 4, 11, 2010, value=1000, rel="<")  # boundary and '<': kept
    assert chembl.drug_target_links(c, "curated+activity", 2015) == [
        ("CHEMBL1", "P42345"), ("CHEMBL4", "P62942")]


def test_cutoff_is_a_parameter():
    c = _db()
    _act(c, 1, 11, 2014)
    assert chembl.drug_target_links(c, "curated+activity", 2014) == []
    assert chembl.drug_target_links(c, "curated+activity", 2015) == [("CHEMBL1", "P62942")]


def test_curated_is_a_subset_of_curated_plus_activity():
    c = _db()
    c.execute("INSERT INTO drug_mechanism VALUES (1, 11)")
    _act(c, 1, 10, 2010)
    assert set(chembl.drug_target_links(c, "curated")) <= set(
        chembl.drug_target_links(c, "curated+activity", 2015))


def test_bad_definition_and_wrong_release_are_refused(tmp_path):
    with pytest.raises(ValueError):
        chembl.drug_target_links(_db(), "by-name")
    p = tmp_path / "x.db"
    db = sqlite3.connect(p)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO version VALUES ('ChEMBL_20', '2015-02-02', '')")
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="ChEMBL_19"):
        chembl.connect(p)


@pytest.mark.skipif(not chembl.DB_PATH.exists(), reason="ChEMBL 19 snapshot not downloaded")
def test_real_snapshot_sirolimus_links():
    c = chembl.connect()
    sirolimus = c.execute("SELECT chembl_id FROM molecule_dictionary "
                          "WHERE lower(pref_name) = 'sirolimus'").fetchone()[0]
    assert len(chembl.approved_parents(c)) == 1885
    curated = {a for d, a in chembl.drug_target_links(c, "curated") if d == sirolimus}
    both = {a for d, a in chembl.drug_target_links(c, "curated+activity", 2015) if d == sirolimus}
    assert curated == {"P62942"}                # FKBP1A only: the pre-registered Analysis 1 gap
    assert {"P62942", "P42345"} <= both         # mTOR appears only under Analysis 2

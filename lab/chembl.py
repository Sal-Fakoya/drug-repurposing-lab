"""ChEMBL 19 loader: approved parent molecules and drug-to-gene links (gene = UniProt accession).

Pre-registered link definitions (docs/cutoff-decision.md), applied identically to every drug:
  "curated":          drug_mechanism rows only (Analysis 1, primary).
  "curated+activity": curated plus human IC50/Ki/Kd <= 1000 nM in documents dated before the
                      cutoff (Analysis 2, sensitivity).
Targets are matched by component_sequences.accession, NEVER by name: in ChEMBL 19, target
CHEMBL2842 is labelled "FK506 binding protein 12" but carries P42345 (mTOR).
Read-only; the pool is every approved (max_phase 4) molecule collapsed to its parent.
"""
import sqlite3
from pathlib import Path

from lab import CUTOFF_YEAR

DB_PATH = (Path(__file__).resolve().parent.parent / "data" / "raw" / "chembl19"
           / "chembl_19_sqlite" / "chembl_19.db")
DEFINITIONS = ("curated", "curated+activity")

# Every form (salt, hydrate, parent) of an approved parent molecule, with that parent's molregno.
# Approved parents are exactly the max_phase 4 molecules that are their own parent, plus the 65
# approved molecules that have no hierarchy row. Starting from this small set keeps queries fast.
FORMS = """WITH forms(molregno, parent) AS (
    SELECT h.molregno, h.parent_molregno FROM molecule_hierarchy h
      JOIN molecule_dictionary p ON p.molregno = h.parent_molregno WHERE p.max_phase = 4
    UNION SELECT molregno, molregno FROM molecule_dictionary WHERE max_phase = 4
      AND molregno NOT IN (SELECT molregno FROM molecule_hierarchy))"""
# One row per human protein component of the target, matched by accession.
ACCESSIONS = """
    JOIN target_dictionary t ON t.tid = {tid}
    JOIN target_components tc ON tc.tid = t.tid
    JOIN component_sequences cs ON cs.component_id = tc.component_id
    WHERE t.organism = 'Homo sapiens' AND cs.accession IS NOT NULL"""
CURATED_SQL = f"""{FORMS}
    SELECT DISTINCT f.parent, cs.accession FROM forms f
    JOIN drug_mechanism dm ON dm.molregno = f.molregno
    {ACCESSIONS.format(tid="dm.tid")}"""
# A '>' or NULL relation does not show a value <= 1000 nM, so only '=', '<', '<=' count.
# ponytail: curation flags (data_validity_comment, confidence_score) are not pre-registered, so unused.
ACTIVITY_SQL = f"""{FORMS}
    SELECT DISTINCT f.parent, cs.accession FROM forms f
    JOIN activities a ON a.molregno = f.molregno
    JOIN assays s ON s.assay_id = a.assay_id
    JOIN docs d ON d.doc_id = a.doc_id
    {ACCESSIONS.format(tid="s.tid")}
      AND a.standard_type IN ('IC50', 'Ki', 'Kd') AND a.standard_units = 'nM'
      AND a.standard_value <= 1000 AND a.standard_relation IN ('=', '<', '<=')
      AND d.year IS NOT NULL AND d.year < ?"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the snapshot read-only and refuse any release other than ChEMBL 19."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    name = conn.execute("SELECT name FROM version").fetchone()[0]
    if name != "ChEMBL_19":
        raise ValueError(f"{path} is {name}, expected ChEMBL_19 (last release before the cutoff)")
    return conn


def _chembl_ids(conn: sqlite3.Connection) -> dict[int, str]:
    return dict(conn.execute("SELECT molregno, chembl_id FROM molecule_dictionary"))


def approved_parents(conn: sqlite3.Connection) -> list[str]:
    """ChEMBL ids of every approved parent molecule, sorted. 1885 in ChEMBL 19."""
    ids = _chembl_ids(conn)
    return sorted(ids[r[0]] for r in conn.execute(f"{FORMS} SELECT DISTINCT parent FROM forms"))


def drug_target_links(conn: sqlite3.Connection, definition: str,
                      cutoff_year: int = CUTOFF_YEAR) -> list[tuple[str, str]]:
    """Sorted unique (drug_chembl_id, uniprot_accession) pairs for approved parents, human only."""
    if definition not in DEFINITIONS:
        raise ValueError(f"definition must be one of {DEFINITIONS}, got {definition!r}")
    pairs = set(conn.execute(CURATED_SQL))
    if definition == "curated+activity":
        pairs |= set(conn.execute(ACTIVITY_SQL, (cutoff_year,)))
    ids = _chembl_ids(conn)
    return sorted((ids[m], acc) for m, acc in pairs)

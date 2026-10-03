-- Run against the pinned snapshot:  sqlite3 data/raw/chembl14/chembl_14.db < scripts/check_chembl14.sql
-- Confirm table and column names against chembl_14_erd.png first. Old releases differ from today's schema.

.headers on
.mode column

-- 1. Approved drugs (max_phase 4). This is the drug pool before any filtering.
SELECT COUNT(*) AS approved_molecules FROM molecule_dictionary WHERE max_phase = 4;

-- 2. Is the target drug in the pool? (sirolimus is also known as rapamycin)
SELECT molregno, chembl_id, pref_name, max_phase
FROM molecule_dictionary
WHERE lower(pref_name) IN ('sirolimus', 'rapamycin');

-- 3. Curated mechanism table, if this release has it.
SELECT COUNT(*) AS mechanism_rows FROM drug_mechanism;

-- 4. Targets linked to the target drug through curated mechanism (must include mTOR, UniProt P42345).
SELECT md.pref_name, td.chembl_id AS target, td.pref_name AS target_name, cs.accession
FROM molecule_dictionary md
JOIN drug_mechanism dm ON dm.molregno = md.molregno
JOIN target_dictionary td ON td.tid = dm.tid
LEFT JOIN target_components tc ON tc.tid = td.tid
LEFT JOIN component_sequences cs ON cs.component_id = tc.component_id
WHERE lower(md.pref_name) IN ('sirolimus', 'rapamycin');

-- 5. Fallback if drug_mechanism is missing or empty: potent human activities published up to 2012.
SELECT DISTINCT md.pref_name, td.chembl_id AS target, td.pref_name AS target_name, d.year
FROM molecule_dictionary md
JOIN activities act ON act.molregno = md.molregno
JOIN assays a ON a.assay_id = act.assay_id
JOIN target_dictionary td ON td.tid = a.tid
JOIN docs d ON d.doc_id = a.doc_id
WHERE lower(md.pref_name) IN ('sirolimus', 'rapamycin')
  AND d.year <= 2012
  AND act.standard_type IN ('IC50', 'Ki', 'Kd')
  AND act.standard_units = 'nM'
  AND act.standard_value <= 1000
  AND td.organism = 'Homo sapiens';

-- 6. Pool size after requiring at least one curated target link.
SELECT COUNT(DISTINCT md.molregno) AS approved_with_target
FROM molecule_dictionary md
JOIN drug_mechanism dm ON dm.molregno = md.molregno
WHERE md.max_phase = 4;

-- Follow-up to check_chembl.sql. In ChEMBL 19 the curated mechanism of sirolimus, everolimus and
-- temsirolimus points at FKBP1A (CHEMBL1902), not at mTOR. These queries find out how far that goes.
-- Run:  python scripts/run_sql.py data/raw/chembl19/chembl_19_sqlite/chembl_19.db scripts/check_chembl_mtor.sql
-- Column names are from memory of the old schema: an ERROR line names the culprit, send it to me.

-- A. Does this release have an mTOR target at all (UniProt P42345)?
SELECT td.chembl_id, td.pref_name, td.target_type, td.organism
FROM target_dictionary td
JOIN target_components tc ON tc.tid = td.tid
JOIN component_sequences cs ON cs.component_id = tc.component_id
WHERE cs.accession = 'P42345';

-- B. Recorded activities of the rapamycin analogues on any target containing mTOR, document year up to 2014.
SELECT md.pref_name, td.chembl_id AS target, td.pref_name AS target_name,
       act.standard_type, act.standard_value, act.standard_units, d.year
FROM molecule_dictionary md
JOIN activities act ON act.molregno = md.molregno
JOIN assays a ON a.assay_id = act.assay_id
JOIN target_dictionary td ON td.tid = a.tid
JOIN target_components tc ON tc.tid = td.tid
JOIN component_sequences cs ON cs.component_id = tc.component_id
JOIN docs d ON d.doc_id = a.doc_id
WHERE cs.accession = 'P42345'
  AND lower(md.pref_name) IN ('sirolimus', 'everolimus', 'temsirolimus')
  AND d.year <= 2014
ORDER BY md.pref_name, d.year
LIMIT 40;

-- C. Mechanism text and comments for the rapamycin analogues (may mention mTOR in free text).
SELECT md.pref_name, dm.action_type, dm.mechanism_of_action, dm.mechanism_comment, dm.molecular_mechanism
FROM molecule_dictionary md
JOIN drug_mechanism dm ON dm.molregno = md.molregno
WHERE lower(md.pref_name) IN ('sirolimus', 'everolimus', 'temsirolimus');

-- D. Approved molecules sharing the FKBP1A target. They tie with sirolimus under a gene set containing FKBP1A.
SELECT md.pref_name, md.max_phase, dm.mechanism_of_action
FROM drug_mechanism dm
JOIN molecule_dictionary md ON md.molregno = dm.molregno
JOIN target_dictionary td ON td.tid = dm.tid
WHERE td.chembl_id = 'CHEMBL1902' AND md.max_phase = 4
ORDER BY md.pref_name;

-- E. Pool size after merging salts and forms to the parent molecule.
SELECT COUNT(DISTINCT mh.parent_molregno) AS approved_parents_with_target
FROM molecule_dictionary md
JOIN molecule_hierarchy mh ON mh.molregno = md.molregno
JOIN drug_mechanism dm ON dm.molregno = md.molregno
WHERE md.max_phase = 4;

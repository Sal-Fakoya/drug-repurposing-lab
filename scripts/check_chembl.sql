-- Run against the pinned snapshot, for example:
--   sqlite3 data/raw/chembl19/<unpacked folder>/chembl_19.db < scripts/check_chembl.sql
-- Find the .db with:  find data/raw -name "*.db"
-- Old releases differ from today's schema. If a query errors (missing table or column), the
-- sqlite3 shell prints the error and carries on: note which one, that is information too.

.headers on
.mode column

-- 0. Which release is this? Must say ChEMBL_19 (the last release before the 2015 cutoff).
SELECT * FROM version;

-- 1. Approved molecules (max_phase 4). The drug pool before any filtering.
SELECT COUNT(*) AS approved_molecules FROM molecule_dictionary WHERE max_phase = 4;

-- 2. Are the key drugs in the snapshot, and approved?
--    sirolimus = the target drug, siltuximab and tocilizumab = IL-6 decoys, anakinra = IL-1 route.
SELECT molregno, chembl_id, pref_name, max_phase
FROM molecule_dictionary
WHERE lower(pref_name) IN ('sirolimus', 'rapamycin', 'siltuximab', 'tocilizumab', 'anakinra',
                           'rituximab', 'thalidomide')
ORDER BY pref_name;

-- 3. Does this release have curated mechanisms?
SELECT COUNT(*) AS mechanism_rows FROM drug_mechanism;

-- 4. Curated targets for those drugs, with UniProt accession.
--    Expected (verify): sirolimus -> mTOR P42345, tocilizumab -> IL6R P08887,
--    siltuximab -> IL6 P05231, anakinra -> IL1R1 P14778.
SELECT md.pref_name, dm.mechanism_of_action, td.chembl_id AS target,
       td.pref_name AS target_name, cs.accession
FROM molecule_dictionary md
JOIN drug_mechanism dm ON dm.molregno = md.molregno
JOIN target_dictionary td ON td.tid = dm.tid
LEFT JOIN target_components tc ON tc.tid = td.tid
LEFT JOIN component_sequences cs ON cs.component_id = tc.component_id
WHERE lower(md.pref_name) IN ('sirolimus', 'rapamycin', 'siltuximab', 'tocilizumab', 'anakinra')
ORDER BY md.pref_name;

-- 5. Fallback if drug_mechanism is missing or sirolimus has no mTOR row above:
--    potent human activities published up to 2014, filtered by document year.
SELECT DISTINCT md.pref_name, td.chembl_id AS target, td.pref_name AS target_name, d.year
FROM molecule_dictionary md
JOIN activities act ON act.molregno = md.molregno
JOIN assays a ON a.assay_id = act.assay_id
JOIN target_dictionary td ON td.tid = a.tid
JOIN docs d ON d.doc_id = a.doc_id
WHERE lower(md.pref_name) IN ('sirolimus', 'rapamycin')
  AND d.year <= 2014
  AND act.standard_type IN ('IC50', 'Ki', 'Kd')
  AND act.standard_units = 'nM'
  AND act.standard_value <= 1000
  AND td.organism = 'Homo sapiens';

-- 6. Pool size after requiring at least one curated target link.
SELECT COUNT(DISTINCT md.molregno) AS approved_with_target
FROM molecule_dictionary md
JOIN drug_mechanism dm ON dm.molregno = md.molregno
WHERE md.max_phase = 4;

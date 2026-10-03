# Cutoff decision record

Commit this file BEFORE running the lab on real data. It is the evidence that the cutoff was
chosen from the literature, not from how well the lab ranked the target drug.

Status: CHOSEN as 2015 by Thierry. Awaiting Sal's confirmation.
Decided on (date and time): ________   Confirmed by: ________ and ________

## Convention

`CUTOFF_YEAR=N` is exclusive: evidence must be published before 1 January N, so dated up to
N-1-12-31. Provisional choice: **N = 2015** (publications up to 2014-12-31).
Change it everywhere with `python scripts/set_cutoff.py <year>`, then run `pytest -q`.

## The rule, stated before the lab was run

Choose the earliest cutoff where (a) the canary query (disease with sirolimus, rapamycin or
mTOR, excluding HHV-8, Kaposi and HIV papers) returns zero title/abstract matches, and
(b) at least three independent sources report incomplete response or no response to IL-6
blockade. The rule is ad hoc, not a published standard. It was proposed before the evidence
below was read.

## Sweep (Europe PMC, title and abstract only, published up to the stated date)

| Up to | Disease | IL-6 | Tocilizumab | IL-6 non-response (loose) | Siltuximab | Canary | Canary excl. viral |
|---|---|---|---|---|---|---|---|
| 2012-12-31 | 2363 | 300 | 46 | 40 | not counted | 7 | 0 |
| 2013-12-31 | 2512 | 329 | 60 | 46 | 2 | 9 | 0 |
| 2014-12-31 | 2657 | 362 | 71 | 56 | 6 | 9 | 0 |
| 2015-12-31 | 2799 | 393 | 87 | 65 | 21 | 9 | 0 |

All canary matches are HHV-8, Kaposi sarcoma or transplant papers. No title or abstract links
iMCD to sirolimus or mTOR before 2016.

## Evidence that IL-6 blockade does not help every patient

| PMID | Published | What it reports | Available at cutoff |
|---|---|---|---|
| 20501803 | 2010 | Case refractory to an anti-IL-6 antibody and other treatments, then responded to anakinra | 2013 |
| 23659971 | 2013-05 | Phase I siltuximab, mixed diseases: 86% of Castleman patients improved on at least one clinical component, but only 12 of 36 evaluable had a radiologic response | 2014 |
| 25042199 | 2014-07 | Randomised trial in HIV-negative, HHV-8-seronegative patients: durable response in 18 of 53 (34%) on siltuximab versus 0 of 26 on placebo | 2015 |
| 25110138 | 2014-08 | Review: siltuximab approved for HIV-negative, HHV-8-negative MCD in April and May 2014 | 2015 |

Counter-evidence read: 23801137 (11 of 12 tocilizumab-treated patients improved), 20676969,
23163599 (HHV-8-positive), 23718671. The record "PReS-FINAL-2198: Insufficient efficacy of
tocilizumab therapy in children with Castleman's disease" has no abstract in Europe PMC, so
the lab cannot cite it. It is not counted.

Cutoff 2013 has one source (a single case). Cutoff 2014 adds a mixed-disease phase I. Cutoff
2015 is the earliest with three independent sources, including the randomised trial.

## Why not later

Later cutoffs add more post-approval siltuximab literature, sit closer to the period when
sirolimus was first used in iMCD, and are not needed to satisfy the rule.

## Known confounds and limits

- A literature route exists from Castleman disease through HHV-8 (KSHV) to PI3K/AKT/mTOR
  (PMID 23316192, January 2013). iMCD is HHV-8-negative. The graph method must exclude or
  separately report HHV-8 and Kaposi papers.
- Year-only dates are stored as 1 January, so records near a cutoff can be misdated by months.
- The phase I trial (23659971) mixes lymphoma, myeloma and Castleman patients.
- Sources disagree on when the first patient was treated with sirolimus (2012 versus 2014).
  This test concerns published knowledge, not that private timeline. Do not claim the clock
  was set before treatment began.
- Counts use title and abstract only. Full-text matches inflate the default Europe PMC search.

## Data pins required by this cutoff

Verified from public sources:
- ChEMBL 19 is dated July 2014 in ChEMBL's release list. The ChEMBL 20 FTP folder is dated
  2015-02-02, so ChEMBL 19 is the last release before the cutoff and ChEMBL 20 must NOT be used.
- ChEMBL has provided SQLite builds since release 19, and has since built them for all releases.
- MSigDB v5.0 support was added to GSEA in June 2015, so v5.0 is after the cutoff.
  v4.0 is most likely the last release before it (date not directly verified).
- Open Targets: not usable, no release before 2016.

To confirm and record (fill in):
- [ ] The chembl_19 FTP folder exists and the file names are as expected: ________
- [ ] `SELECT * FROM version` in the downloaded database says ChEMBL_19.
- [ ] Sirolimus is in the pool (max_phase 4) and links to mTOR (UniProt P42345).
- [ ] Siltuximab and tocilizumab are present and link to IL-6 and IL-6R.
- [ ] Pool definition and size N: ________ (see data/README.md)
- [ ] Pathway gene sets from MSigDB version ________ (archive page checked, license accepted).
- [ ] mTOR and IL-6 gene sets exist in that release: set names ________
- [ ] Every source and what could still leak is recorded in LIMITATIONS.md.

## Suggested research question at this cutoff

"For patients whose disease does not respond to IL-6 blockade, which approved drug should be
tested next?" This frames the lab around the clinical gap in the evidence, without claiming
what any individual did.



## ChEMBL 19 pin (results of scripts/check_chembl.sql)

- Version table: ChEMBL_19, created 2014-07-03.
- Approved molecules (max_phase 4): 2759. With a curated mechanism target link: 1773.
  Both counts are before merging salts and forms to the parent molecule.
- Present and approved: sirolimus, everolimus, temsirolimus, siltuximab, tocilizumab,
  anakinra, rituximab, thalidomide.
- Curated targets: siltuximab -> IL6 (P05231), tocilizumab -> IL6R (P08887), anakinra -> IL1R1
  (P14778). Sirolimus, everolimus and temsirolimus -> FKBP1A (P62942), "FK506-binding protein 1A
  inhibitor". No mTOR (P42345) link appears in the curated mechanism or in the potent-activity
  fallback (document year up to 2014).
- Consequence: sirolimus can reach an mTOR hypothesis only if a gene set from the pre-cutoff
  pathway source contains FKBP1A. Gene sets must NOT be edited by hand to create the link.
  If no link exists, report it as a limitation of this data layer.
- Still to fill in: MSigDB version ________; FKBP1A present in mTOR sets: ________;
  results of scripts/check_chembl_mtor.sql: ________.

## Bridge evidence (abstracts read)

- Supports: sirolimus complete responses in autoimmune lymphoproliferative syndrome
  (PMID 19208097, small series, different disease).
- Does not support: IL-6 activating PI3K/Akt/mTOR. PMID 12242656 reports IGF-1 but not IL-6
  increased Akt/P70S6K phosphorylation. PMID 12953803 describes IL-6 acting through JAK/STAT
  and MAPK.
- 114 of 144 sirolimus-lymphoproliferative records are transplant papers, so a naive
  disease-label co-mention link would credit sirolimus for the wrong reason.
- Expectation: sirolimus may not reach the top 10. This is an acceptable, reportable outcome.

## Pre-registered evaluation (fixed before the lab runs on real data)

- Primary: rank of sirolimus as the mid-rank of its tie group (scoring.log_target_rank_eval_only).
- Secondary: best mid-rank among the rapamycin analogues (sirolimus, everolimus, temsirolimus).
- Baselines: random order (many seeds), literature co-occurrence, LLM-only, no-reopen ablation.
- Outcome categories: sirolimus in top 10 / another rapamycin analogue in top 10 / neither.
- Decided on ________ by ________ and ________.

## ChEMBL 19 pin (scripts/check_chembl.sql and check_chembl_mtor.sql)

- Version table: ChEMBL_19, created 2014-07-03.
- Approved molecules (max_phase 4): 2759. Approved parent molecules with a curated mechanism
  target: 1617 (pool size N under the curated definition).
- Present and approved: sirolimus, everolimus, temsirolimus, siltuximab, tocilizumab, anakinra,
  rituximab, thalidomide.
- Curated mechanism targets: siltuximab -> IL6 (P05231), tocilizumab -> IL6R (P08887),
  anakinra -> IL1R1 (P14778). Sirolimus, everolimus, temsirolimus -> FKBP1A (P62942).
- mTOR (P42345) is in this release as target CHEMBL2842, named "FK506 binding protein 12", and
  as the complex CHEMBL2221341 (mTORC1). Targets MUST be matched by UniProt accession, never name.
- Sirolimus has potent recorded activity on CHEMBL2842 in documents up to 2014 (IC50 0.1, 0.45,
  1.6, 3.47 and 10 nM; one 10000 nM). Temsirolimus has one value (1760 nM). Everolimus has none
  in this snapshot: a ChEMBL coverage difference, not a biological one.
- Approved molecules with curated target FKBP1A (they tie under a gene set containing it):
  everolimus, pimecrolimus, sirolimus, tacrolimus, temsirolimus.

## Pre-registered drug-target link definitions (fixed before the lab runs on real data)

- Analysis 1 (primary): a drug links to a gene if ChEMBL lists it as a curated mechanism target.
- Analysis 2 (sensitivity, reported alongside): curated targets plus human targets with a recorded
  IC50, Ki or Kd of 1000 nM or less in a document dated before the cutoff.
- Both rules apply identically to every drug. Gene sets are never edited by hand. Both analyses
  are reported whatever they show. The primary was chosen knowing that sirolimus links to mTOR
  only under Analysis 2.
- Still to fill in: MSigDB version ________; FKBP1A present in the mTOR gene sets: ________.

## Bridge evidence (abstracts read)

- Supports: sirolimus complete responses in autoimmune lymphoproliferative syndrome
  (PMID 19208097, small series, different disease).
- Does not support: IL-6 activating PI3K/Akt/mTOR. PMID 12242656 reports IGF-1 but not IL-6
  increased Akt/P70S6K phosphorylation. PMID 12953803 describes IL-6 acting through JAK/STAT
  and MAPK.
- 114 of 144 sirolimus-lymphoproliferative records are transplant papers, so a naive disease-label
  co-mention link would credit sirolimus for the wrong reason.
- Expectation: sirolimus may not reach the top 10. This is an acceptable, reportable outcome.

## Pre-registered evaluation (fixed before the lab runs on real data)

- Primary: rank of sirolimus as the mid-rank of its tie group (scoring.log_target_rank_eval_only).
- Secondary: best mid-rank among sirolimus, everolimus and temsirolimus.
- Run under both link definitions above.
- Baselines: random order (many seeds), literature co-occurrence, LLM-only, no-reopen ablation.
- Outcome categories: sirolimus in top 10 / another rapamycin analogue in top 10 / neither.
- Decided on ________ by ________ and ________.

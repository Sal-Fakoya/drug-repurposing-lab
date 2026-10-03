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

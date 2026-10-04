# Cutoff decision record

Commit this file BEFORE running the lab on real data. It is the evidence that the cutoff was
chosen from the literature, not from how well the lab ranked the target drug.

Status: CONFIRMED as 2015 by Thierry and Sal
Decided on (date and time): 2026-10-03 16:26 CDT (UTC-05:00)   Confirmed by: Thierry Donambi and Sal Fakoya

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
- MSigDB, verified on Broad's archived downloads page: v3.1 September 2012, v4.0 May 2013,
  v5.0 April 2015 (v5.1 January 2016). v5.0 is after the cutoff, so v4.0 is the last release
  before it and is the pin. (GSEA software support for v5.0 came in June 2015, also after.)
- Open Targets: not usable, no release before 2016.

To confirm and record (fill in):
- [x] The chembl_19 FTP folder exists and the file names are as expected: `ChEMBLdb/releases/chembl_19/`
      lists `chembl_19_sqlite.tar.gz` (2,471,647,673 bytes, SHA-256
      984bc5c4d50a6424d5f2452bb809a50d1249bbb73b07eb70f3655b6827c5120f). EBI publishes no
      checksum for this release, so the hash is pinned in `setup_data.py` from our first download.
- [x] `SELECT * FROM version` in the downloaded database says ChEMBL_19 (created 2014-07-03).
- [x] Sirolimus is in the pool (max_phase 4). It links to mTOR (UniProt P42345) only under Analysis 2
      (recorded activity). Its curated link (Analysis 1) is FKBP1A (P62942) only.
- [x] Siltuximab and tocilizumab are present and link to IL-6 (P05231) and IL-6R (P08887), curated.
- [x] Pool definition and size N: `lab.chembl.POOL_DEFINITION`: approved (max_phase 4) parent
      molecules with at least one human target (curated link, matched by UniProt accession).
      N = 1146 (of 1885 approved parents). The same pool is used for both analyses; Analysis 2
      adds targets to these drugs, never drugs (amendment of 2026-10-04, see "ChEMBL 19 pin").
      Drug-target pairs in the pool: 3779 curated, 5516 with Analysis 2.
- [ ] Pathway gene sets from MSigDB v4.0 (May 2013), downloaded 2026-10-04 from Broad's archived
      downloads page, `msigdb_v4.0_files_to_download_locally.zip`, SHA-256
      8b4096da2b979ebd474cadb3e72b1528388578acc5adde062ec2b45435c523fe.
      Licence accepted: ________ (Thierry to confirm).
- [x] mTOR and IL-6 gene sets exist in that release (collection `c2.cp`): BIOCARTA_MTOR_PATHWAY,
      KEGG_MTOR_SIGNALING_PATHWAY, PID_MTOR_4PATHWAY, REACTOME_MTORC1_MEDIATED_SIGNALLING;
      BIOCARTA_IL6_PATHWAY, PID_IL6_7PATHWAY. The full list is fixed by the term rule below.
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
  inhibitor". No mTOR (P42345) link appears in the curated mechanism. The potent-activity fallback
  does link sirolimus to mTOR once targets are matched by UniProt accession (target CHEMBL2842 is
  named "FK506 binding protein 12" but carries P42345); see "ChEMBL 19 pin" below.
- Consequence: sirolimus can reach an mTOR hypothesis only if a gene set from the pre-cutoff
  pathway source contains FKBP1A. Gene sets must NOT be edited by hand to create the link.
  If no link exists, report it as a limitation of this data layer.
- MSigDB version and the FKBP1A result: see "MSigDB v4.0 pin" below. Results of
  scripts/check_chembl_mtor.sql: see "ChEMBL 19 pin" below.

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
- Decided on Oct 4 by Thierry and Sal.

## ChEMBL 19 pin (scripts/check_chembl.sql and check_chembl_mtor.sql)

- Version table: ChEMBL_19, created 2014-07-03.
- Approved molecules (max_phase 4): 2759. Drug pool (pool size N): 1146 approved parent molecules
  with at least one human target (curated drug_mechanism link, Homo sapiens, matched by UniProt
  accession), salts and other forms merged to the parent. The same pool is used for both link
  definitions (lab.chembl.POOL_DEFINITION; data/README.md).
- Amendment, 2026-10-04, before any lab run on real data: this line first gave N = 1617, which
  counted every approved parent with any drug_mechanism row, including non-human targets
  (bacteria, viruses, fungi, parasites) and mechanism rows with no target. The loader always
  used human targets only. N is now 1146 everywhere; decided by Sal Fakoya.
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

## MSigDB v4.0 pin (May 2013)

- Source and hash: see the checklist above.
- **Collection: `c2.cp` (canonical pathways) only** (1320 sets in the file, 1302 after mapping).
  `c2.all` is excluded on purpose: its chemical and genetic perturbation sets include
  drug-treatment signatures (for example rapamycin response), which would leak drug identity
  through set membership. The snapshot also contains `c2.all`, but no hypothesis may use it.
  (Sal, 2026-10-04.)
- FKBP1A (P62942) is in 11 `c2.cp` sets, mostly NFAT, TGF-beta and T-cell calcium signalling. Of the
  mTOR sets, only BIOCARTA_MTOR_PATHWAY (23 genes, also contains MTOR) has it. It is absent from
  KEGG_MTOR_SIGNALING_PATHWAY, PID_MTOR_4PATHWAY, BIOCARTA_IGF1MTOR_PATHWAY and
  REACTOME_MTORC1_MEDIATED_SIGNALLING.
- So Analysis 1 reaches sirolimus only through a gene set that contains FKBP1A, and which mTOR set
  a hypothesis resolves to decides whether it does. This is a known property of the data, not
  something to engineer around.
- Neither IL-6 set (BIOCARTA_IL6_PATHWAY, PID_IL6_7PATHWAY) contains FKBP1A or MTOR: the IL-6 to
  mTOR link has to come from the literature bridge.
- Term to gene set is a mechanical rule, not a hand-picked list: every `c2.cp` set whose name
  contains MTOR, IL6, JAK_STAT or VEGF (rule and resulting list drafted by Sal, committed
  separately). Order of events, for the record: FKBP1A membership was observed on 2026-10-04 while
  pinning MSigDB, before this rule was written. The rule keys on names only and applies to every
  term, so it does not choose sets by drug membership, but the result was known when it was drafted.
- Symbol to UniProt mapping uses ChEMBL 19's own `component_synonyms` (July 2014), implemented in
  `lab/msigdb.py`: a symbol with one accession maps to it; an ambiguous symbol (an alias of several
  genes) is excluded and counted; a symbol ChEMBL does not know is dropped and counted. In `c2.cp`
  55% of gene slots are unmapped (35724 of 64505) and 352 are ambiguous, because ChEMBL only
  knows proteins that are compound targets. No ChEMBL drug can hit a dropped gene, so dropping
  matches what drugs can target, but it shrinks gene sets and the hypergeometric universe. Sal
  reviewed this rule on 2026-10-04: no objection.
- Gene set sizes under the rule, before -> after mapping (symbols -> mapped). Sets with fewer than
  10 mapped genes are flagged TINY: their p-values are coarse. No minimum size is pre-registered,
  so tiny sets are kept and only flagged. Regenerate from `gene_set_report_c2.cp.json` in the
  snapshot once the rule is committed.
  - name contains MTOR (6 sets; contain FKBP1A: BIOCARTA_MTOR_PATHWAY):
      BIOCARTA_IGF1MTOR_PATHWAY: 20 -> 14
      BIOCARTA_MTOR_PATHWAY: 23 -> 13
      KEGG_MTOR_SIGNALING_PATHWAY: 52 -> 34
      PID_MTOR_4PATHWAY: 69 -> 38
      REACTOME_ENERGY_DEPENDENT_REGULATION_OF_MTOR_BY_LKB1_AMPK: 18 -> 12
      REACTOME_MTORC1_MEDIATED_SIGNALLING: 11 -> 6 (TINY)
  - name contains IL6 (2 sets; contain FKBP1A: none):
      BIOCARTA_IL6_PATHWAY: 22 -> 20
      PID_IL6_7PATHWAY: 47 -> 32
  - name contains JAK_STAT (2 sets; contain FKBP1A: none):
      KEGG_JAK_STAT_SIGNALING_PATHWAY: 155 -> 55
      ST_JAK_STAT_PATHWAY: 9 -> 5 (TINY)
  - name contains VEGF (6 sets; contain FKBP1A: none):
      BIOCARTA_VEGF_PATHWAY: 29 -> 20
      KEGG_VEGF_SIGNALING_PATHWAY: 76 -> 59
      PID_VEGFR1_2_PATHWAY: 69 -> 52
      PID_VEGFR1_PATHWAY: 26 -> 19
      PID_VEGF_VEGFR_PATHWAY: 10 -> 6 (TINY)
      REACTOME_VEGF_LIGAND_RECEPTOR_INTERACTIONS: 10 -> 5 (TINY)

## Pre-registered drug-target link definitions (fixed before the lab runs on real data)

- Analysis 1 (primary): a drug links to a gene if ChEMBL lists it as a curated mechanism target.
- Analysis 2 (sensitivity, reported alongside): curated targets plus human targets with a recorded
  IC50, Ki or Kd of 1000 nM or less in a document dated before the cutoff. Only activity
  relations `=`, `<` and `<=` count: a `>` relation or a missing relation does not show a value
  of 1000 nM or less. Documents with no year are excluded. Human targets, matched by UniProt
  accession, salts collapsed to the parent molecule.
- Both rules apply identically to every drug. Gene sets are never edited by hand. Both analyses
  are reported whatever they show. The primary was chosen knowing that sirolimus links to mTOR
  only under Analysis 2.
- MSigDB version and the FKBP1A result: see "MSigDB v4.0 pin" above.

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
- Decided on Oct 4 by Thierry and Sal.

## Amendment, 2026-10-04: feasibility check, analysis roles, gene-set rule

Recorded before any lab run on real data and before any run uses the drug mask. It adds to the
"MSigDB v4.0 pin" section above, which already records the FKBP1A observation and the order of
events.

### Disclosure: what we looked at before the run

On 2026-10-04 Sal Fakoya, working with Claude Code, inspected the real data layer: the ChEMBL 19
and MSigDB v4.0 snapshot for cutoff 2015 (`lab.snapshot`, sha256
`57be32ea9e0064f44bc1ae5ed582380880937d046b9169ee237ea09305d3804a`; pool 1146 drugs, 3779 curated
and 5516 curated+activity links). We therefore know these facts about the target before the
replay:

- Sirolimus (CHEMBL413) is in the 1146-drug pool. Its curated target is FKBP1A (P62942) only.
  Under curated+activity it also links to MTOR (P42345), EIF4E (P06730) and FKBP5 (Q13451).
- Tocilizumab: IL6R (P08887). Siltuximab: IL6 (P05231). Both are the same under both definitions.
- Five pool drugs have FKBP1A as their only curated target: sirolimus, everolimus, temsirolimus,
  tacrolimus, pimecrolimus.
- MSigDB v4.0 c2.cp sets containing the genes MTOR / FKBP1A / IL6: 58 / 11 / 37 (103 distinct).
- Method A scored on each of those sets alone, over the whole pool (not a lab run):
  - curated: sirolimus scores only through the 11 FKBP1A sets, at best mid-rank 3.0 in a five-way
    tie with the four drugs above, and between mid-rank 573.5 and 631 in each of the 92 MTOR-only
    or IL6 sets (it has no overlap with them, so it sits in the large tie group of drugs that
    score zero);
  - curated+activity: rank 1, untied, in BIOCARTA_MTOR_PATHWAY and several mTOR and PI3K sets.

### Analysis roles: unchanged

The curated definition stays the primary analysis (Analysis 1) and curated plus activity
<= 1000 nM stays the sensitivity analysis (Analysis 2). Both are run and reported whatever they
show. Neither the roles nor the two link definitions were changed after seeing the facts above.

Two other choices were made on the same day, after the FKBP1A observation had been recorded in
"MSigDB v4.0 pin". They are stated here so they can be judged: the drug pool was restricted to
drugs with at least one human target (1146 drugs, see "ChEMBL 19 pin"), and hypotheses may use
only the `c2.cp` collection, not `c2.all`. The recorded reasons are that drugs without a human
target can never score against human gene sets and would inflate the random baseline, and that
`c2.all` holds drug-treatment signatures (for example rapamycin response) that would leak drug
identity. Neither choice adds a route to sirolimus: the first shrinks the pool, and the second
removes routes (for example PARENT_MTOR_SIGNALING_UP, a `c2.all` set containing both FKBP1A and
MTOR).

### The gene-set rule as implemented

`find_gene_set(term, cutoff_year)` implements the rule recorded in "MSigDB v4.0 pin" (every c2.cp
set whose name contains the term's keyword) as `lab.msigdb.match_term`,
`RULE_VERSION = "c2cp-name-contains-v1"`, applied identically to every term, whether it comes
from the configuration or from an agent. The keyword is made mechanically from the term:

1. Upper-case the term and remove any separator between a letter and a following digit
   ("IL-6" and "IL 6" give IL6).
2. Split on every other character that is not a letter or digit.
3. Drop these words: SIGNALING, SIGNALLING, SIGNAL, PATHWAY, PATHWAYS, THE, OF, AND, BY,
   VIA, IN.
4. Join what is left with underscores ("JAK-STAT signaling" gives JAK_STAT).

A set matches when its name, without the source prefix (the text before the first underscore,
such as BIOCARTA or KEGG), contains the keyword. Only sets in the snapshot (at least one gene
mapped to a UniProt accession) are candidates. The result is the sorted list of matches. A term
with no keyword matches nothing. No synonyms, no fuzzy matching, no manual additions or removals.
If nothing matches, the hypothesis is not testable by methods A and B and must say
`testable: false`.

On the snapshot above this reproduces the lists recorded in "MSigDB v4.0 pin" exactly for the
configured terms: "mtor signaling" 6 sets, "IL-6 signaling" 2, "jak-stat signaling" 2,
"vegf signaling" 6. A token-based variant was drafted first and dropped in favour of the rule
recorded first; both were mechanical and both include BIOCARTA_MTOR_PATHWAY, the only mTOR set
containing FKBP1A.

One configuration term was changed to fit the rule: `experiments/config/real.json`
"interleukin-6 signaling" became "IL-6 signaling", because the rule does not match spelled-out
names. The other three terms already matched and are unchanged.

### Masking

A drug mask exists (salt fingerprint 3ffadf45, created 2026-10-04 on one machine and shared
privately); no lab run has used it yet. The target's masked id stays in the eval folder
(`LAB_EVAL_DIR`, by default `~/.drug_lab_eval`) and is not printed or recorded anywhere else.

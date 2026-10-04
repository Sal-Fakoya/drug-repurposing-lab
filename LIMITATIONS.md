# Limitations and validation still needed

## Leakage controls
- Date filter on all literature retrieval, cutoff 2015 (enforced by policy and by the tool).
- Drug and disease names masked in scoring (enforced by policy, test in tests/).
- Rankings come only from computed scores, never from the LLM.
- Planner reward is label-free. The target drug rank is evaluation only.
- Canary check on the bare model: not run. We have no record of what the bare model says about the
  disease and the drug.

## Sources that cannot be rolled back to the cutoff
- Europe PMC titles and abstracts are served as they are today. Records are filtered by
  firstPublicationDate before 1 January 2015, but the text of a record may differ from its original
  form, and year-only dates are stored as 1 January, so records near the cutoff can be misdated by
  months. citedByCount, text-mined annotations and MeSH terms are not used: they are computed today
  and would leak later knowledge.
- Model weights. The language models were trained on text from after the cutoff and may remember
  the answer. This cannot be rolled back. Masked drug ids, the LLM-only baseline and the canary
  check are the controls.
- ChEMBL 19 (2014-07-03) and MSigDB v4.0 (May 2013) are pinned releases, so they are rolled back.
  What they do not capture: curated mechanism rows carry no date, and ChEMBL's coverage differs by
  drug (everolimus has no recorded potent activity in this release: a coverage gap, not biology).
- Open Targets is not used: it has no release before 2016.

## Known limits
- Single case (iMCD and sirolimus). Sparse rare disease literature.
- The model may remember the answer when proposing hypotheses. The LLM-only baseline measures this.
- Under the primary analysis ChEMBL 19 links sirolimus only to FKBP1A, so it can only be ranked
  through gene sets that contain FKBP1A, where it ties with everolimus, temsirolimus, tacrolimus
  and pimecrolimus. mTOR appears only under the sensitivity analysis (see the decision record).
- Gene sets are mapped to UniProt through ChEMBL 19's own synonyms: about 55% of c2.cp gene slots
  are unmapped and dropped, and ambiguous aliases are excluded. This shrinks sets and the
  hypergeometric universe. Some sets end up tiny (fewer than 10 mapped genes, for example
  ST_JAK_STAT_PATHWAY), and their p-values are coarse.
- The term-to-gene-set rule is mechanical (the set name contains the keyword), so it misses sets
  spelled differently, for example IL_6 against IL6.
- A literature route from Castleman disease through HHV-8 to PI3K/AKT/mTOR exists, but iMCD is
  HHV-8-negative, so HHV-8 and Kaposi papers are excluded or reported separately. 114 of 144
  sirolimus and lymphoproliferative records are transplant papers, so a naive co-mention link would
  credit sirolimus for the wrong reason.
- Sources disagree on when the first patient was treated with sirolimus (2012 versus 2014). This
  test concerns published knowledge, not that private timeline.
- Toy mode uses synthetic data. Toy results are never reported as findings.

## Validation needed before any real-world use
- Laboratory and clinical validation. Outputs are agent-generated hypotheses, not treatment advice.

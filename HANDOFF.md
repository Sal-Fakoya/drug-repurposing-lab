# Handoff to Claude Code

You are joining a two-person team mid-sprint. Thierry (me) built the data layer, scaffold and
documentation. Sal owns the agents, orchestration, scoring and evaluation. This file is my
handoff; read the files it points to before changing anything.

## What we are building

Hack-Nation 7th Global AI Hackathon, Challenge 03 (Databricks Agentic Scientific Discovery, built
with Omnigent). The deliverable is a multi-agent "lab" that replays rare-disease drug repurposing
with the literature clock set back, and measures how fast it rediscovers a known answer. The case
is idiopathic multicentric Castleman disease (iMCD) and sirolimus. The primary metric is the
tie-group mid-rank of sirolimus; see docs/cutoff-decision.md for the full pre-registered design.

## Read these first, in this order

1. README.md: scaffold, run commands, scoring.
2. docs/cutoff-decision.md: cutoff year, drug-target link definitions, bridge evidence,
   pre-registered evaluation. **This is the sign-off record; do not change it without me.**
3. LIMITATIONS.md: known confounds (HHV-8/mTOR route, transplant co-mention, ChEMBL coverage).
4. agents/lab_director.yaml: the Omnigent agent spec.
5. agents/README.md: Sal's nine Omnigent checks. He owns these.
6. lab/scoring.py and lab/tools.py: method A (hypergeometric), method B (literature graph),
   ledger, planner. Sal rewrote these on commit 3bd6c5f. Treat his version as authoritative.
7. tests/: 56 tests pass on main as of my last pull. Keep them green.

## What is decided and NOT up for debate without me or Sal

- Cutoff year: 2015 (publications dated up to 2014-12-31). Change it with
  `python scripts/set_cutoff.py <year>`, never by hand.
- Data pins: ChEMBL 19 (July 2014) at data/raw/chembl19/chembl_19_sqlite/chembl_19.db; MSigDB
  version yet to pick (last release before 2015). Open Targets is unusable (no pre-2016 release).
- Target matching: by UniProt accession, never by name. In ChEMBL 19, target CHEMBL2842 is
  mislabelled "FK506 binding protein 12" but carries accession P42345 (mTOR). A name-based
  loader will silently miss sirolimus's mTOR link.
- Drug-target link definitions, pre-registered:
  - Analysis 1 (primary): curated drug_mechanism rows only.
  - Analysis 2 (sensitivity, reported alongside): curated plus human IC50/Ki/Kd ≤1000 nM in
    documents dated before the cutoff.
  Both rules apply identically to every drug. Gene sets are never edited by hand.
- Target drug rank lives in an eval-only artefact. The planner, Analysis agent and bandit must
  never read it. Agents operate on masked drug IDs.
- Everything the Literature agent returns must have `firstPublicationDate` before the cutoff.
  Do not use citedByCount, text-mined annotations or MeSH terms: they are computed today and
  leak post-cutoff knowledge.
- Branch workflow: name branches `thierry/<topic>` or `claude/<topic>`, run
  `ruff check . && python -m pytest -q` before every push, open a PR, let CI pass, self-merge.
  Do not push directly to main.

## State of play (updated by me on each handoff)

- Cutoff sweep done, 2013-2016. Record in docs/cutoff-decision.md.
- Canary query (disease AND sirolimus/rapamycin/mTOR, excluding HHV-8/Kaposi/HIV): 0 pre-cutoff
  records at 2015. Pre-cutoff IL-6 non-response evidence: ~3 independent sources at 2015
  including the siltuximab randomised trial.
- ChEMBL 19 check (scripts/check_chembl.sql, check_chembl_mtor.sql, run_sql.py): sirolimus is in
  the pool, approved, with potent recorded activity on mTOR via UniProt accession. Curated
  mechanism points at FKBP1A only; five drugs tie on it (sirolimus, everolimus, temsirolimus,
  tacrolimus, pimecrolimus). Pool size: 1146 approved parent molecules with at least one human
  target, merged to parents (definition in data/README.md; an earlier count of 1617 included
  non-human targets and was corrected).
- MSigDB: NOT downloaded yet. Needed to decide whether Analysis 1 can reach sirolimus.
- Loaders: NOT written. lab/scoring.py still runs on lab/toy_data.py.
- Open PR: #3 (thierry/bridge-evidence-docs). Contains the decision record and the ChEMBL
  scripts. Awaiting Sal's review.
- Sal's nine Omnigent checks in agents/README.md: status unknown, ask him.

## Pending work, in rough priority

1. **MSigDB pin.** Download the last release before 2015 (likely v4.0, verify). Put files in
   data/raw/ (git-ignored). Check: do mTOR gene sets contain FKBP1A? Record the version and the
   result in docs/cutoff-decision.md. One shell step, no code.
2. **Real-data loaders.** Replace lab/toy_data.py with:
   - A ChEMBL 19 loader producing drug→gene links (list[tuple[drug_chembl_id, uniprot_accession]])
     under BOTH definitions above. Match targets by `component_sequences.accession`. Human only.
   - An MSigDB loader producing gene sets (dict[set_name, set[uniprot_accession or gene symbol]]).
   - A snapshot function that writes a deterministic, hashable artefact (parquet or JSON) under
     data/snapshots/<cutoff>/ for the scoring code to read.
   Must fit Sal's current lab/scoring.py (commit 3bd6c5f: hypergeometric method A, tie-aware
   target rank). Do NOT modify scoring.py or tools.py without flagging it to Sal first.
3. **Masked drug pool.** masked_drug_pool(cutoff_year) currently returns toy IDs. Make it return
   masked IDs for every approved parent molecule in the ChEMBL 19 snapshot. The mapping between
   masked IDs and ChEMBL IDs lives in an eval-only file the agents cannot read.
4. **Baselines.** Random (many seeds), literature co-occurrence, LLM-only, no-reopen ablation.
   Pre-registered in docs/cutoff-decision.md.
5. **Dashboard.** HTML snapshot the demo reads, not the live DB. Safety banner required.

## Rules for Claude Code

- **Read before you write.** Open the files listed above before changing anything.
- **Do not touch** docs/cutoff-decision.md, agents/, lab/scoring.py, lab/tools.py or
  tests/test_tools.py without asking me first. Sal and I own those.
- **Before every push:** `ruff check . && python -m pytest -q`. If either fails, stop and show me.
- **Branches and PRs**, never direct push to main. Branch name `claude/<topic>`. CI must be
  green before you self-merge, and you only self-merge files I asked you to change.
- **Never fabricate data.** No invented ChEMBL IDs, PMIDs or UniProt accessions. If you need a
  value you cannot find in the pinned snapshot or in Europe PMC with the pre-cutoff filter,
  stop and ask.
- **Never hand-edit gene sets** to make a drug link to a target. If the pre-cutoff pathway source
  does not connect them, report it as a limitation.
- **Match ChEMBL targets by UniProt accession, never by name.**
- **No cutoff leaks.** Any ChEMBL activity, publication date or document year used must be before
  1 January of the cutoff year defined in lab.CUTOFF_YEAR.
- When unsure, read docs/cutoff-decision.md and ask me rather than guessing.

## Project map

agents/ # Omnigent spec (Sal), README with his nine checks
contracts/ # JSON schemas for ledger objects
docs/ # cutoff-decision.md (sign-off record)
lab/ # scoring (Sal), tools (Sal), ledger, policies, toy_data
policies/ # server_config.yaml
scripts/ # set_cutoff.py, check_europepmc.py, check_chembl*.sql,
# run_sql.py, triage_abstracts.py, summarize_bridge.py, toy_loop.py
tests/ # 56 passing on main
data/raw/ # git-ignored. ChEMBL and MSigDB files land here.
docs/ # cutoff-decision.md


## How to ask me

I am in the chat that started this handoff. If you are about to make a judgment call affecting
the pre-registered design, the data pins, Sal's code, or the demo claim, pause and ask me there.
Small, obvious cleanups inside your remit do not need to ask.
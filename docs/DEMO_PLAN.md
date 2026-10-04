# Plan: run the backtest with LLM agents, score it, and build the demo

Goal: run the Omnigent agent lab on the real iMCD / sirolimus replay (cutoff 2015), score it as a
backtest against baselines, and present the result with the static dashboard.

Status of this plan: updated after PR #31 (real-mode scoring, method A only). Items marked
"depends on" are waiting on another PR or person.

## Ground rules (from HANDOFF.md, do not break)

- Do not edit `docs/cutoff-decision.md`, `agents/`, `lab/scoring.py`, `lab/tools.py` or
  `tests/test_tools.py` without asking Thierry or Sal first.
- Change the cutoff only with `python scripts/set_cutoff.py <year>`. The project cutoff is 2015.
- Never fabricate data (no invented ChEMBL IDs, PMIDs or UniProt accessions).
- Match ChEMBL targets by UniProt accession, never by name.
- Agents must never read the eval-only files (target drug rank, target id, drug names, mask).
- Before every push: `ruff check . && python -m pytest -q`. If either fails, stop and report.
- Work on a branch named `claude/<topic>`. Open a PR, never push to main.
- Keep the safety banner on all output: "Agent-generated hypotheses. Not medical advice. Needs laboratory and clinical validation."
- Do not publish MSigDB-derived content (gene sets or gene lists) under the legacy licence.

## How the pieces connect

```
Omnigent agents --write_ledger / run_experiment--> ledger/runtime/*.jsonl   (agent-visible)
                                           \-----> eval-only files          (target rank, target id, names, mask)

ledger rows --> dashboard/build.py   --> static HTML   (presentation only, no live link to agents)
eval-only   --> experiments/evaluate.py --> results.md, results.csv, rank-vs-experiments plot
```

The dashboard has no connection to the agents. It renders a snapshot of a finished run's ledger.
The backtest numbers come from `experiments/evaluate.py`, not from the dashboard.

## Where things stand

Done and merged on main (per the owner's notes): dashboard restyle (#25), mask handling (#24),
decision-record pins (#23), MSigDB v4.0 pin, ChEMBL 19 checks.

Done, open:
- PR #31, real-mode scoring, method A only. CI green, mergeable, awaiting Sal's review.
  - Real pool is 1,146 masked ids. The target mid-rank is identical across seeds.
  - Under curated links the mTOR sets give mid-rank 8.5. Under curated plus activity the
    target is rank 1. Non-mTOR sets give a large tie group, about 580 to 600.
  - Tie-aware Borda, no ranking truncation, a real negative control (8 genes, seed 20150101),
    and `LAB_LINK_DEFINITION` (read in `scoring.link_definition()`) to pick the analysis.
  - A missing mask, an unknown gene set or an unknown id fails closed.
- PR #26 (safe mask default, forced rotation keeps a backup), #29 and #30 (docs). CI green.
  Sal said she will merge #26, #29, #30 and #25.
- PR #32 (this plan).

## Step 0: Check current state

- [ ] Read `HANDOFF.md`, `README.md`, `agents/README.md`, `experiments/README.md`, `data/README.md`.
- [ ] Confirm which of #26, #29, #30, #31 and Sal's ledger PR have merged. Rebase or merge main into the working branch.
- [ ] Run `python -m pytest -q` and `ruff check .` to confirm a green start.
- [ ] Report anything missing before continuing.

## Step 1: Real data (on the machine that holds `data/raw/`)

`data/raw/` is git-ignored and lives on the owner's local computer. These steps run there.

- [ ] Expect ChEMBL 19 at `data/raw/chembl19/chembl_19_sqlite/chembl_19.db` and the MSigDB v4.0 GMT files under `data/raw/msigdb/`.
- [ ] Confirm `lab.CUTOFF_YEAR` is 2015.
- [ ] Build the snapshot the lab reads: `python -m lab.snapshot 2015`. Optional parquet export: `python scripts/build_snapshots.py`.
- [ ] Verify the drug pool is 1,146 approved parent molecules and that the manifest hashes check.
- [ ] Confirm the mask exists and is stored where agents cannot read it. The masked-to-ChEMBL mapping is eval-only.
- [ ] Set `LAB_TARGET_DRUG` to the target's masked id only through the eval-only path. Never put it in a prompt or an agent-visible file.
- [ ] Confirm the terms in `experiments/config/real.json` before the first run.

## Step 2: Run the agents with an LLM

Requires Python 3.12 or newer.

```bash
uv tool install "omnigent[databricks,tracing]"
omnigent setup                      # add a model credential
pip install -e .                    # same environment, so lab.* imports work
```

- [ ] Set `executor.model` in `agents/lab_director.yaml` to a model id that exists in the workspace (ask Sal, she owns `agents/`).
- [ ] Fix the prompt in `scripts/run_demo.sh`: it says cutoff 2013, the project cutoff is 2015. Sal's ledger PR is expected to include this fix. Depends on: Sal's ledger PR.
- [ ] Work through the nine checks in `agents/README.md`, and record the answers there.
- [ ] Real mode plans method A only (method B has no real loader). Confirm `lab.available_methods()` reflects that.
- [ ] Do a fresh run per analysis, each into its own directory:

```bash
export LAB_MODE=real
export LAB_LINK_DEFINITION=curated            # Analysis 1, primary
export LAB_RUNTIME_DIR=ledger/runs/curated_001
scripts/run_demo.sh

export LAB_LINK_DEFINITION=curated+activity   # Analysis 2, sensitivity
export LAB_RUNTIME_DIR=ledger/runs/activity_001
scripts/run_demo.sh
```

- [ ] Confirm each run produced ledger rows (hypotheses, experiment specs, results, verdicts, final ranking).
- [ ] Confirm no run read an eval-only file.

## Step 3: Score it as a backtest

```bash
LAB_MODE=real LAB_LINK_DEFINITION=curated LAB_TARGET_DRUG=<masked id> \
python experiments/evaluate.py --agent-ledger ledger/runs/curated_001

LAB_MODE=real LAB_LINK_DEFINITION=curated+activity LAB_TARGET_DRUG=<masked id> \
python experiments/evaluate.py --agent-ledger ledger/runs/activity_001
```

- [ ] Output lands in `experiments/out/real/`: `results.md`, `results.csv`, `target_rank_vs_experiments.png`. Keep the two analyses in separate output directories (use `--out`).
- [ ] Compare the arms: `agent_omnigent` (real LLM run), `agent` (LLM-free pipeline), `random`, `no_reopen`, `cooccurrence`.
- [ ] Report two metrics per analysis: experiments until the target enters the top 10, and final mid-rank.
- [ ] Report both analyses side by side, as pre-registered. Do not pick the better one.
- [ ] Expect the curated analysis to be tied (mid-rank 8.5 in mTOR sets, five-way FKBP1A tie) and the activity analysis to rank the target first. Say so plainly.

## Step 4: Build the dashboard

```bash
python dashboard/build.py --mode real --out dashboard/out/index.html
```

- [ ] Depends on: Sal's ledger PR (exports in the runtime folder, `ledger.rows`). The dashboard results need both.
- [ ] Pass the run's ledger rows to the dashboard.
- [ ] Confirm the safety banner shows, and that no "SYNTHETIC" bar shows in real mode.
- [ ] Add the results, ranking and reasoning-trail sections `build.py` says are "added in later steps".
- [ ] Embed or link the rank-vs-experiments plot and the `results.md` table for both analyses.
- [ ] Add the footer with the ChEMBL attribution.
- [ ] Add a test that no gene lists ever appear on the page.
- [ ] Check that all file-derived text is HTML-escaped (Europe PMC text is untrusted).

## Step 5: Demo or go live

- [ ] Safest demo: use the pre-recorded runs. Present `dashboard/out/index.html` next to the results plot.
- [ ] Optional live segment: run `omnigent run agents/lab_director.yaml` in a terminal, then rebuild the dashboard from the new ledger.
- [ ] Hosting: the page is static. Do not host MSigDB-derived content under the legacy licence. The owner's recommendation is their own VPS with nginx. Fill in `deploy/README.md` with the chosen route.
- [ ] A button in the dashboard that triggers agents is not built. Do not promise it.

## Open items and owners

| Item | Owner | Status |
|---|---|---|
| Review PR #31 (tie-aware Borda, no truncation, real negative control, `LAB_LINK_DEFINITION`) | Sal | open |
| Ledger PR (exports, `ledger.rows`, `run_demo.sh` fix) | Sal | being tracked down |
| Merge #26, #29, #30 | Sal | CI green |
| Canary check and LLM-only baseline | Sal | not run |
| Decision-record blanks (licence line, "Decided on" lines) | Thierry | open |
| Real runs for both analyses, then record the demo | Thierry, Sal | blocked on the ledger PR and #31 |
| Dashboard results, footer and no-gene-list test | Thierry | blocked on the ledger PR |
| Hosting | Thierry | not started |
| Confirm the submission deadline on the event page (believed to be 9:00 AM ET, unverified) | Thierry | open |

## Known gaps to report honestly

- Method B has no real loader. Real runs use method A only.
- The LLM-only baseline is not implemented.
- The secondary metric (best mid-rank among sirolimus, everolimus, temsirolimus) is not implemented.
- Outcome categories (target in top 10 / another analogue in top 10 / neither) are not implemented.
- Method A has a known circular z that fails the negative control.
- In toy mode the planner performs no better than random, so expect weak planner evidence.
- The curated analysis cannot separate sirolimus from the other four FKBP1A drugs, so its result is a tie group, not a clean win.
- Toy output is never a finding. Label it clearly.

## Done when

- [ ] Real-mode LLM runs exist with ledgers on disk, one per analysis.
- [ ] `results.md` compares each with the baselines.
- [ ] `dashboard/out/index.html` renders the runs with the safety banner and the ChEMBL footer.
- [ ] Tests and lint pass.
- [ ] The gaps above are stated in the final report.

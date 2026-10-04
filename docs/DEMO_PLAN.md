# Plan: run the backtest with LLM agents, score it, and build the demo

Goal: run the Omnigent agent lab on the real iMCD / sirolimus replay (cutoff 2015), score it as a
backtest against baselines, and present the result with the static dashboard.

## Ground rules (from HANDOFF.md, do not break)

- Do not edit `docs/cutoff-decision.md`, `agents/`, `lab/scoring.py`, `lab/tools.py` or
  `tests/test_tools.py` without asking Thierry or Sal first.
- Change the cutoff only with `python scripts/set_cutoff.py <year>`. The project cutoff is 2015.
- Never fabricate data (no invented ChEMBL IDs, PMIDs or UniProt accessions).
- Match ChEMBL targets by UniProt accession, never by name.
- Agents must never read the eval-only file (target drug rank).
- Before every push: `ruff check . && python -m pytest -q`. If either fails, stop and report.
- Work on a branch named `claude/<topic>`. Open a PR, never push to main. Do not open a PR unless asked.
- Keep the safety banner on all output: "Agent-generated hypotheses. Not medical advice. Needs laboratory and clinical validation."

## How the pieces connect

```
Omnigent agents --write_ledger / run_experiment--> ledger/runtime/*.jsonl   (agent-visible)
                                           \-----> eval-only file           (target rank, hidden from agents)

ledger rows --> dashboard/build.py   --> static HTML   (presentation only, no live link to agents)
eval-only   --> experiments/evaluate.py --> results.md, results.csv, rank-vs-experiments plot
```

The dashboard has no connection to the agents. It renders a snapshot of a finished run's ledger.
The backtest numbers come from `experiments/evaluate.py`, not from the dashboard.

## Step 0: Check current state

- [ ] Read `HANDOFF.md`, `README.md`, `agents/README.md`, `experiments/README.md`, `data/README.md`.
- [ ] Confirm which handoff items are still open: MSigDB pin, real-data loaders, masked drug pool, baselines.
- [ ] Run `python -m pytest -q` and `ruff check .` to confirm a green start.
- [ ] Report anything missing before continuing.

## Step 1: Real data

- [ ] Put ChEMBL 19 at `data/raw/chembl19/chembl_19_sqlite/chembl_19.db` and the last pre-2015 MSigDB release in `data/raw/` (git-ignored).
- [ ] Confirm `lab.CUTOFF_YEAR` is 2015.
- [ ] Build snapshots: `python scripts/build_snapshots.py`, which writes `data/snapshots/<cutoff>/`.
- [ ] Verify the drug pool is 1146 approved parent molecules (see `data/README.md`).
- [ ] Record the MSigDB version and whether mTOR gene sets contain FKBP1A in `docs/cutoff-decision.md` (ask Thierry first, this file is a sign-off record).
- [ ] Find the masked ID for sirolimus from the eval-only mapping. Do not expose it to agents. Use it only as `LAB_TARGET_DRUG`.
- [ ] Confirm the terms in `experiments/config/real.json` before the first run.

## Step 2: Run the agents with an LLM

Requires Python 3.12 or newer.

```bash
uv tool install "omnigent[databricks,tracing]"
omnigent setup                      # add a model credential
pip install -e .                    # same environment, so lab.* imports work
```

- [ ] Set `executor.model` in `agents/lab_director.yaml` to a model id that exists in the workspace (ask Sal, he owns `agents/`).
- [ ] Fix the prompt in `scripts/run_demo.sh`: it says cutoff 2013, the project cutoff is 2015.
- [ ] Work through the nine checks in `agents/README.md`, and record the answers there.
- [ ] Do a fresh run into a known directory:

```bash
export LAB_MODE=real
export LAB_RUNTIME_DIR=ledger/runs/run_001
scripts/run_demo.sh
```

- [ ] Confirm the run produced ledger rows (hypotheses, experiment specs, results, verdicts, final ranking).
- [ ] Confirm the run never read the eval-only file.

## Step 3: Score it as a backtest

```bash
LAB_MODE=real LAB_TARGET_DRUG=<masked id of sirolimus> \
python experiments/evaluate.py --agent-ledger ledger/runs/run_001
```

- [ ] Output lands in `experiments/out/real/`: `results.md`, `results.csv`, `target_rank_vs_experiments.png`.
- [ ] Compare the arms: `agent_omnigent` (real LLM run), `agent` (LLM-free pipeline), `random`, `no_reopen`, `cooccurrence`.
- [ ] Report two metrics: experiments until the target enters the top 10, and final mid-rank of sirolimus.
- [ ] Do a second pass under the sensitivity link definition (Analysis 2) and report both.

## Step 4: Build the dashboard

```bash
python dashboard/build.py --mode real --out dashboard/out/index.html
```

- [ ] Pass the run's ledger rows to the dashboard. If `build.py` has no way to take a ledger directory, add that.
- [ ] Confirm the safety banner shows, and that no "SYNTHETIC" bar shows in real mode.
- [ ] Finish the sections `build.py` says are "added in later steps": results, ranking, reasoning trail.
- [ ] Embed or link the rank-vs-experiments plot and the `results.md` table.
- [ ] Check that all file-derived text is HTML-escaped (Europe PMC text is untrusted).

## Step 5: Demo or go live

- [ ] Safest demo: use the pre-recorded run. Present `dashboard/out/index.html` next to the results plot.
- [ ] Optional live segment: run `omnigent run agents/lab_director.yaml` in a terminal, then rebuild the dashboard from the new ledger.
- [ ] Hosting: the HTML is static. Any static host works (GitHub Pages, S3, a Databricks App). Fill in `deploy/README.md` with the chosen route.
- [ ] A button in the dashboard that triggers agents is not built. Do not promise it.

## Known gaps to report honestly

- Real-data loaders may still be unwritten (check `lab/scoring.py` and `find_gene_set` in `lab/tools.py`).
- The LLM-only baseline is not implemented.
- The secondary metric (best mid-rank among sirolimus, everolimus, temsirolimus) is not implemented.
- Outcome categories (target in top 10 / another analogue in top 10 / neither) are not implemented.
- Method A has a known circular z that fails the negative control.
- In toy mode the planner performs no better than random, so expect weak planner evidence.
- Toy output is never a finding. Label it clearly.

## Done when

- [ ] A real-mode LLM run exists with a ledger on disk.
- [ ] `experiments/out/real/results.md` compares it with the baselines.
- [ ] `dashboard/out/index.html` renders that run with the safety banner.
- [ ] Tests and lint pass.
- [ ] The limitations above are stated in the final report.

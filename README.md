# Hack-Nation-Hackathon-Team-Nebula - Drug Repurposing Lab

# Drug Repurposing Lab

An agentic lab built with Omnigent for Hack-Nation Challenge 03. It replays a known discovery
(iMCD and sirolimus) with the clock set to 2015 and measures how fast an adaptive agent loop
ranks the known drug compared with baselines.

> Agent-generated hypotheses. Not medical advice. Needs laboratory and clinical validation.

## Live demo and status (4 Oct 2026)

Dashboard: https://drug-repurposing-lab.netlify.app/ (a static page built from one real run, with names withheld).

What it shows: one real run on the pinned ChEMBL 19 and MSigDB v4.0 snapshot (cutoff 2015, curated links, method A only, 1,146-drug pool). Across 20 results the target's mid-rank stayed in the large tie group near the middle of the pool in 19, and was rank 6 in one. The lab did not rediscover the answer in this run. Treat it as a first, unreplicated result, not a finding.

Not done yet:
- Real-mode scoring is in PR #31 (open). The run above used that branch.
- Analysis 2 (curated plus recorded activity) has not been run.
- Method A failed its own negative control (top score about 1.9, above the 1.0 threshold), and `compile_final_ranking` still includes results from a method whose control failed.
- The Haiku 4.5 director over-reports ("no contradictions", "all checks passed"); read the ledger, not the narration.
- Method B has no real loader. The canary check and the LLM-only baseline are not done (`LIMITATIONS.md`).
- Open PRs: #26, #29, #30 (masking default, decision-record follow-ups, limitations), #34 (dashboard footer), and the dashboard tabs and chart branch `claude/dashboard-index`.
- Do not publish MSigDB-derived content: the legacy licence is for internal research only.

## How the layers fit together

| Layer | Lives in | Does | Never does |
|---|---|---|---|
| LLM agents | `agents/lab_director.yaml` | Read evidence, propose hypotheses, choose tests, interpret results | Produce drug rankings |
| Python tools | `lab/tools.py`, `lab/scoring.py` | Fetch dated data, score drugs, run the bandit | Make judgment calls |
| Policies | `lab/policies.py` | Allow, deny or ask on every tool call | Reason about science |
| Ledger | `lab/ledger.py`, `contracts/` | Validate and record every object, hand out ids | Expose evaluation-only data |

Agents hand off by id (`hyp_003`, `exp_007`, `res_007`), never by pasting text. The target
drug's rank is written to an evaluation-only file that no agent-facing function reads.

## Quick start (no Omnigent needed)

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                      # 33 tests: contracts, ledger, policies, loop, agent spec
python scripts/toy_loop.py     # whole loop on synthetic data, no LLM
```

Toy mode (`LAB_MODE=toy`, the default) uses synthetic data so the plumbing can be debugged
offline. Toy output is never a finding.

## Run through Omnigent (Python 3.12 or newer)

```
uv tool install "omnigent[databricks,tracing]"
omnigent setup                 # add a model credential
pip install -e .               # in the same environment, so lab.* is importable
scripts/run_demo.sh
```

Work through the nine checks in `agents/README.md` first. They are the things the Omnigent
docs did not settle for us.

## What is verified and what is not

Verified here: schemas, ledger validation, policy verdicts, bandit determinism, masking, the
planner never seeing the target rank, tool allowlists in the YAML, the ChEMBL and MSigDB loaders,
the hash-verified snapshot and the dashboard build (all in `tests/`).

Not verified: the Omnigent behaviors listed in `agents/README.md`, and any result beyond the single run
described above. The real data loaders and the snapshot are written and tested.

## Cutoff convention

`CUTOFF_YEAR=2015` is exclusive: evidence must be published before 1 January 2015 (dated up to 2014-12-31). Every source is pinned to that line or listed in `LIMITATIONS.md`.

## Where to start

Sal: get `omnigent run` working with the director YAML, then work through `agents/README.md`.
Thierry: the loaders, snapshot, masking and dashboard are written. Next is wiring real-mode
scoring (`masked_drug_pool`, `_gene_union`, `target_drug_id`, `unmask`) once the ledger changes
land, then running both analyses.

See `HANDOFF.md` for shift handoffs.

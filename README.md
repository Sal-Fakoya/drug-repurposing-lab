# Hack-Nation-Hackathon-Team-Nebula - Drug Repurposing Lab

# Drug Repurposing Lab

An agentic lab built with Omnigent for Hack-Nation Challenge 03. It replays a known discovery
(iMCD and sirolimus) with the clock set to 2013 and measures how fast an adaptive agent loop
ranks the known drug compared with baselines.

> Agent-generated hypotheses. Not medical advice. Needs laboratory and clinical validation.

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
planner never seeing the target rank, tool allowlists in the YAML (all in `tests/`).

Not verified: running the YAML in Omnigent, the real Europe PMC path (`MODE=real`), the real
data loaders (not written yet), and the Omnigent behaviors listed in `agents/README.md`.

## Cutoff convention

`CUTOFF_YEAR=2013` is exclusive: evidence must be published before 1 January 2013 (dated up to 2012-12-31). Every source is pinned to that line or listed in `LIMITATIONS.md`.

## Where to start

Sal: get `omnigent run` working with the director YAML, then work through `agents/README.md`.
Thierry: replace the `_require_toy()` branches in `lab/scoring.py` and `find_gene_set` in
`lab/tools.py` with reads from date-stamped Delta snapshots, and fill `data/README.md` and
`LIMITATIONS.md` as you pin sources.

See `HANDOFF.md` for shift handoffs.

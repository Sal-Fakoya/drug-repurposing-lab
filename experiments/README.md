# experiments: evaluation harness

Compares the lab pipeline with baselines on the same budget (`LAB_BUDGET`, via
`tools.BUDGET_TOTAL`) and the same data (`lab.scoring`), and scores every arm only from the
eval-only file.

```bash
python experiments/evaluate.py                 # 100 seeds per arm, current LAB_MODE
python experiments/evaluate.py --seeds 20      # quicker
python experiments/evaluate.py --agent-ledger path/to/omnigent/runtime_dir   # add real agent runs
```

Outputs go to `experiments/out/<mode>/` (git-ignored):

- `results.md`, `results.csv`: one row per arm.
- `target_rank_vs_experiments.png`: target mid-rank against experiments run, median and IQR band
  over seeds, all arms on one plot.
- `runs/<arm>/seed_<n>/`: each run's ledger and eval-only file.

## Arms

| Arm | What it is |
|---|---|
| `agent` | The lab pipeline without LLMs: Thompson planner (`planner_select_arms`), runner, `analyze_result`, and a reopen step that proposes the next hypothesis from the config after a contested verdict (standing in for the insight agent). |
| `random` | The same pipeline with the planner replaced by a uniformly random order of untested arms. |
| `no_reopen` | The agent pipeline without the reopen step. |
| `cooccurrence` | One ranking by literature co-occurrence with the disease (`scoring.literature_cooccurrence`); no experiments. |
| `agent_omnigent` | Optional: ledgers from real Omnigent runs (`--agent-ledger`), copied and replayed the same way. |

## Metrics

After every experiment the harness rebuilds the ranking the lab would publish at that point
(`scoring.borda` over results with a supported verdict whose hypothesis is still active, the
rule `tools.compile_final_ranking` uses) and writes the target's **mid-rank** to the eval-only
file. Before any supported result every drug is tied. `metrics.py` reads only those rows:

- **Experiments until the target enters the top 10**: first step with mid-rank at most 10.
- **Final mid-rank**: the target's mid-rank when the run stops (budget spent or no untested arm).

Both are reported as distributions over seeds (median, IQR, best to worst, share reaching the
top 10).

## Toy now, real later

The harness never imports `toy_data` or checks the mode. `LAB_MODE` selects
`config/<mode>.json` (query, initial hypotheses, reopen candidates) and everything else goes
through `lab.tools` and `lab.scoring`. For real mode, set `LAB_MODE=real` and `LAB_TARGET_DRUG`
(the target's masked id), confirm the terms in `config/real.json` before the first run, and wire
the lab's real loaders (`masked_drug_pool`, `find_gene_set`, the scoring methods and
`literature_cooccurrence`). No harness code changes.

## Toy results (100 seeds) and how to read them

Toy results are plumbing checks, never findings.

| Arm | Reached top 10 | Experiments to top 10, median [IQR] | Final mid-rank, median [IQR] |
|---|---:|---:|---:|
| Agent pipeline (Thompson + reopen) | 79% | 6 [4, 7] | 3.5 [3, 20.75] |
| Random arm order (+ reopen) | 77% | 6 [5, 7] | 3.5 [3, 20.75] |
| Agent pipeline without reopen | 0% | - | 30.5 [30.5, 30.5] |
| Literature co-occurrence | 0% | - | 24.5 |

- **The planner is no better than random.** Each arm runs at most once, so the planner only
  ever chooses among untried arms, which share the same optimistic prior: Thompson sampling
  reduces to a random order and the reward history is never used.
- **The gain comes from reopen, partly by construction.** The toy config makes mTOR reachable
  only through the reopen step (mirroring the replay story), so `no_reopen` cannot find the
  target.
- **Method A's "supported" verdicts are uninformative** until its circular z is fixed (it fails
  the negative control), which inflates the supported set the final ranking draws on.

## Not covered yet (from the pre-registered evaluation in docs/cutoff-decision.md)

- LLM-only baseline.
- Secondary metric: best mid-rank among sirolimus, everolimus and temsirolimus.
- Outcome categories (target in top 10 / another analogue in top 10 / neither).
- Running under both drug-target link definitions.

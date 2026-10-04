# How to run a real-mode test

Real mode (`LAB_MODE=real`) scores the masked 1,146-drug pool from the pinned ChEMBL 19 and
MSigDB v4.0 snapshot. Toy mode uses synthetic data. This guide was written from the code on the
`claude/real-scoring` branch (PR #31) and from the toy runs. It has **not** been executed end to end
in real mode with an LLM, so treat unverified steps as the expected path and report what you see.

Run everything on the machine that holds `data/raw/`. It is git-ignored and is not in the cloud
container.

## Before you start

- [ ] **PR #31 must be in the code you run.** At last check it was open and not in `main`
  (real-mode scoring, method A only). Either wait for it to merge, or run from its branch:
  `git fetch origin && git checkout claude/real-scoring`.
- [ ] Python 3.12 or newer for Omnigent (see `docs/SESSION_SUMMARY.md` for the install).
- [ ] An Anthropic API key configured with `omnigent setup`, with credit on it.
- [ ] `data/raw/chembl19/chembl_19_sqlite/chembl_19.db` and the MSigDB v4.0 GMT files under
  `data/raw/msigdb/`.

## Step 1: Build the snapshot

From the repo root, in your `.venv`:

```bash
pip install -e ".[dev,data]"
pytest -q                          # expect all tests to pass
python -m lab.snapshot 2015        # writes data/snapshots/2015/ with a hashed manifest
```

Check the drug pool is 1,146. If not, stop and compare with `data/README.md`.

## Step 2: Create or restore the drug mask

Agents see masked ids (`m_` plus 10 hex digits), never ChEMBL ids or names. The salt is secret and
lives under `data/eval_only/` (git-ignored). Do not let an agent read it.

```bash
python -m lab.masking              # first time only: creates the mask, names and target files
# On another machine, copy the mask.json you were sent into the eval folder, then:
python -m lab.masking restore      # never run init there: it makes a new salt
```

Never rerun init on a machine that already has a mask: a new salt renames every drug and orphans
existing ledger rows. If the project is on an NTFS or FAT mount, file modes are ignored and the
owner-only check fails closed. Set `LAB_EVAL_DIR` to a folder on a Linux filesystem (for example
`~/.lab_eval`) before step 2.

## Step 3: Make an Anthropic copy of the agent YAML

`agents/lab_director.yaml` points at Databricks. Make a copy outside the repo and point it at the
Anthropic API. Do not commit it, and tell Sal (she owns `agents/`).

```bash
sed -e 's/model: databricks-claude-sonnet-4-6/model: claude-sonnet-5-5/' \
    -e 's/, auth: {type: databricks, profile: oss}//' \
    agents/lab_director.yaml > /tmp/lab_director_anthropic.yaml

python - <<'E'
import re
p = "/tmp/lab_director_anthropic.yaml"
t = open(p).read()
t = re.sub(r"  auth:\n    type: databricks\n    profile: oss\s+# your Databricks profile\n", "", t)
open(p, "w").write(t)
E
```

Use **Sonnet 5.5 for the director and the safety agent** at minimum. In the toy runs, Haiku 4.5
finished the loop but the director over-interpreted results and the safety agent invented checks.
If you want to save money, only switch the literature, planner, runner and analysis agents to
`claude-haiku-4-5-20251001` and keep the rest on Sonnet. This split has not been tested.

## Step 4: Restart the Omnigent server, then set the environment

Agent tools run inside a background Omnigent server (port 6767). It keeps the environment it was
started with, so `export` in your shell does not reach the tools if the server is already running.
In the toy runs this sent a ledger to the default folder instead of `LAB_RUNTIME_DIR`.

```bash
omnigent stop                                  # stop the background server

export LAB_MODE=real
export LAB_LINK_DEFINITION=curated             # Analysis 1, primary. Or: curated+activity
export LAB_RUNTIME_DIR=ledger/runs/real_curated_001
# export LAB_EVAL_DIR=~/.lab_eval              # only if you set it in step 2
```

Do not set `LAB_TARGET_DRUG` unless you need to. Real mode reads the target from the eval-only mask
files, and the target must never appear in a prompt or an agent-visible file.

## Step 5: Run it

```bash
omnigent run /tmp/lab_director_anthropic.yaml \
  -p "Run the replay for idiopathic multicentric Castleman disease with cutoff 2015."
```

Real mode plans **method A only**, because method B has no real loader (`lab.available_methods()`).
Expect the run to use many model calls across seven agents. The policy caps a session at 300 tool
calls and $10 (the YAML sets these). Watch your API balance.

## Step 6: Check that the run is valid before you trust it

```bash
ls ledger/runs/real_curated_001/              # ledger.jsonl, eval_only.jsonl, arm_stats.json
python - <<'E'
import json
rows=[json.loads(l) for l in open("ledger/runs/real_curated_001/ledger.jsonl")]
for r in rows:
    if r["kind"] in ("final_ranking","safety_review","approval"):
        p=r["payload"]; print(r["id"], r["kind"], r["ts"])
        if r["kind"]=="final_ranking": print("  res_ids:", p["res_ids"], "hyp_ids:", p["hyp_ids"])
        if r["kind"]=="safety_review":
            print("  passed:", p["passed"])
            for k,v in p["checks"].items(): print("  ",k,":",v)
E
```

Confirm all of these:
- [ ] The ledger is in the folder you set. If it landed in `ledger/runtime/`, the server kept an old
  environment. Run `omnigent stop` and repeat step 4.
- [ ] `synthetic` is `false` on the rows. A `true` means the run was in toy mode.
- [ ] There is one `final_ranking` and one `safety_review`. A duplicate means the first safety call
  succeeded but its output was lost (this happened in the toy runs).
- [ ] The negative control result and its method. Method A failed its control in toy mode. Report
  the real z, whatever it is.
- [ ] `compile_final_ranking` includes results from a method whose control failed (known gap).
  Say so if it does.
- [ ] No `approval` row unless you approved publication.

## Step 7: Score it as a backtest

```bash
LAB_MODE=real LAB_LINK_DEFINITION=curated \
python experiments/evaluate.py --agent-ledger ledger/runs/real_curated_001 \
  --out experiments/out/real_curated
```

Output: `results.md`, `results.csv`, `target_rank_vs_experiments.png`. Compare the real agent run
against the random, no-reopen and co-occurrence arms. Repeat steps 4 to 7 with
`LAB_LINK_DEFINITION=curated+activity` and a new `LAB_RUNTIME_DIR` and `--out`, and report both
analyses side by side, as pre-registered. Do not pick the better one.

Expected from the PR #31 check (owner's run, unverified here): under curated links the target's
mid-rank is 8.5 in the mTOR sets (a tie with the other FKBP1A drugs), and under curated plus
activity it is rank 1.

## Step 8: Approval gate (optional, about 5 minutes)

To exercise the human approval gate, tell the director: "Do not interpret results. Ask safety to
call publish_final_ranking for the final ranking and report the approval prompt exactly." The gate
fires only when safety calls `publish_final_ranking`. A director asking "approve?" in chat is not the
gate. A failed `safety_review` (`passed: false`) should withhold publication. Write down how the
prompt looks and where the approval row is recorded (nine-check item 5 in `agents/README.md`).

## Build the dashboard from a run

```bash
python dashboard/build.py --mode real --out dashboard/out/index.html
```

Skeleton only at last check: banner, provenance and limitations. Results, ranking and the
reasoning trail depend on Sal's ledger PR (exports, `ledger.rows`). Keep the safety banner. Do not
publish MSigDB-derived content under the legacy licence, and never put gene lists on the page.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `NotImplementedError: Real loaders are not wired yet` | You are not running PR #31's code. Checkout `claude/real-scoring` or wait for the merge. |
| Ledger lands in `ledger/runtime/` | Server kept an old env. `omnigent stop`, set env, rerun. |
| Agents fail on first call | The YAML still has the Databricks `auth` block. Redo step 3. |
| Masking error about permissions | NTFS or FAT mount. Set `LAB_EVAL_DIR` to a Linux path and rerun step 2. |
| Missing mask or unknown gene set or id | Real mode fails closed by design. Check steps 1 and 2. |
| Run stops at the cost cap | The $10 or 300-call policy tripped. Check `omnigent usage`, then raise it deliberately. |
| Ledger shows `synthetic: true` | `LAB_MODE` was not `real` inside the server. Restart it with the env set. |

## Rules that still apply

- Do not edit `docs/cutoff-decision.md`, `agents/`, `lab/scoring.py`, `lab/tools.py` or
  `tests/test_tools.py` without asking Thierry or Sal.
- Never fabricate data. Match targets by UniProt accession, never by name.
- Run `ruff check . && python -m pytest -q` before any push.
- Every output carries: "Agent-generated hypotheses. Not medical advice. Needs laboratory and
  clinical validation."

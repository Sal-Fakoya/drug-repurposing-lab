# Session summary (4 Oct 2026): where we left off

Written so work can resume after a session limit reset. Facts below come from what was checked in
the session or from the owner's pasted terminal output. Items marked "unverified" were not checked.

## The project in one paragraph

Drug Repurposing Lab is an Omnigent agent lab for Hack-Nation Challenge 03 (Databricks Agentic
Scientific Discovery). It replays a known discovery with the evidence cutoff at 1 January 2015:
idiopathic multicentric Castleman disease (iMCD) patients who do not respond to IL-6 blockade, and
sirolimus as the target drug. LLM agents propose hypotheses and interpret results but never rank
drugs. Python tools score. A policy layer gates every tool call. An append-only ledger validates
every object. The target's rank is in an evaluation-only file no agent reads. See `README.md`,
`HANDOFF.md` and `docs/cutoff-decision.md` (the sign-off record, do not edit without Thierry or Sal).

## Deadline and submission

- Deadline: **4 Oct 2026, 15:00 GMT+2 (Kigali)**, which is 9:00 AM ET. Uploads and edits stay open
  until 15:15. Team changes close at 15:00.
- Two submissions are required: the HackOS platform and the Google Form
  `https://forms.gle/VS65tsovASMuBwEn9`.
- The platform needs: project name, challenge 03, GitHub repo link, team photo, and three MP4 or
  MOV videos (team intro, product demo, technical walkthrough), each up to 60 seconds and 1 GB.
- Repo: `https://github.com/Sal-Fakoya/drug-repurposing-lab`. Team: Nebula (Salamot Fakoya,
  Thierry Donambi).

## State of the repo and pull requests

| Item | State at last check | Notes |
|---|---|---|
| PR #32 (this branch, `claude/practical-dijkstra-owxei2`) | open, CI green, mergeable, no reviews | `docs/DEMO_PLAN.md` plus these docs |
| PR #31 (`claude/real-scoring`) | open, CI green, no reviews, **not in main** | real-mode scoring, method A only. Sal owns `lab/scoring.py` |
| `thierry/decision-record-blanks` | branch exists | the owner filled the licence and "Decided on" lines |
| #26, #29, #30, #25 | Sal said she would merge | #25 is already in main |
| Sal's ledger PR | not seen | exports, `ledger.rows`, `run_demo.sh` 2013 to 2015 fix |

Check each on GitHub before relying on this table.

## What the real snapshot showed (from the owner's local run, unverified here)

Pool: 1,146 masked approved parent molecules. Under curated links sirolimus has mid-rank 8.5 in the
mTOR gene sets. Under curated plus activity it ranks 1. Non-mTOR sets give a large tie group
(about 580 to 600). Confirm before quoting.

## What was done this session

1. Read the project and explained it.
2. Wrote `docs/DEMO_PLAN.md` (committed, pushed, updated after PR #31) and subscribed to PR #32.
3. Installed Omnigent 0.16.0 in the cloud container and confirmed `agents/lab_director.yaml` loads.
   Could not run agents there (no model credential, no `data/raw/`).
4. Set up Omnigent on the owner's machine with an Anthropic API key. The YAML still pointed at
   Databricks, so an Anthropic copy was made at `/tmp/lab_director_anthropic.yaml` (outside the repo).
5. Ran the full agent loop twice in toy mode (synthetic data).

## Findings from the two toy runs

**Both runs completed the loop.** Ledgers: `ledger/runs/toy_sonnet` and `ledger/runs/toy_haiku`.
Both are git-ignored.

**Sonnet 5.5 run.** Four rounds, `fin_002`, `saf_002` passed. The first safety call returned no
output but did run: `fin_001` and `saf_001` exist, then `fin_002` duplicated it. `saf_001` had the
better caveats (non-independent Borda votes, uncalibrated confidence). Nothing published.

**Haiku 4.5 run.** Completed nine experiments and `fin_001`, but `saf_001` has `passed: False`.
The director's commentary over-interpreted ("Clinical implication", "reflects true biology"),
which its own prompt forbids. The safety agent invented one check (`all_9_results_aggregated`).
Do not use this run's narration. Use the ledger.

**Confirmed in the Haiku ledger:**
- `exp_005` is the method A negative control and it failed (z = 3.107). The Sonnet run showed the
  same z, so it is deterministic. `exp_009` (method B control) passed (z = 0.345, per the director).
- `fin_001` is built from `res_001`, `res_002` (method A) and `res_007`, `res_008` (method B). So
  `compile_final_ranking` keeps results from a method whose own control failed. This is a gap in
  `lab/tools.py` (Sal's file) to report. It is toy mode, so it is not a scientific result.

**Environment gotcha.** `omnigent run` talks to a background server on port 6767. Agent tools run
inside that server, so `export LAB_*` in your shell does not reach them if the server was already
running. The Haiku ledger landed in `ledger/runtime/` instead of `LAB_RUNTIME_DIR`. Restart the
server (`omnigent stop`) before runs that depend on env vars. See `docs/REAL_RUN_GUIDE.md`.

**Approval gate.** The director asking "approve fin_001?" in chat is not the gate. The gate
(`approval_gate` policy) fires when safety calls `publish_final_ranking`. Not yet exercised. No
approval row exists in either ledger.

## Known gaps

- Method B has no real loader. Real mode plans method A only.
- LLM-only baseline, secondary metric (best mid-rank among sirolimus, everolimus, temsirolimus) and
  outcome categories are not implemented.
- Method A has a circular z that fails the negative control.
- The curated analysis cannot separate sirolimus from the other FKBP1A drugs (a tie group).
- The nine Omnigent checks in `agents/README.md` have no recorded answers on `main`.
- `scripts/run_demo.sh` on `main` still says cutoff 2013. Use 2015.
- No real-mode LLM run has been done yet.

## Open items

| Item | Owner |
|---|---|
| Review and merge PR #31 | Sal |
| Ledger PR, canary check, LLM-only baseline | Sal |
| Report the compile-step gap and the silent first safety call | Thierry to Sal |
| Record nine-check answers in `agents/README.md` | Sal, Thierry |
| Real runs for both analyses (see `docs/REAL_RUN_GUIDE.md`) | Thierry, Sal |
| Dashboard results, ChEMBL footer, no-gene-list test | Thierry |
| Hosting (do not publish MSigDB-derived content under the legacy licence) | Thierry |
| Merge the decision-record branch | Thierry |

## Appendix A: video scripts (about 60 seconds each)

Check the two bracketed numbers before saying them.

**Team introduction**
> We are Team Nebula, two people building for Challenge 03.
> I'm Thierry. I built the data layer: pinned, date-stamped snapshots of ChEMBL 19 and MSigDB
> version 4.0, so nothing published after January 2015 can leak in. I also wrote the decision
> record that fixes our evaluation rules before we ran anything.
> My teammate Sal built the agents, the orchestration, the scoring and the evaluation harness.
> We care about one question: can an agent loop rediscover a drug that was found later, if we hide
> everything the world learned afterwards? We chose idiopathic multicentric Castleman disease and
> sirolimus, a real case where patients stopped responding to IL-6 blockade.
> We are honest about limits. Our dashboard says agent-generated hypotheses, not medical advice.

**Product demo** (use the Sonnet run, say "synthetic")
> This is Drug Repurposing Lab. It replays a known discovery with the clock set to 2015.
> The question is on the page: for patients whose Castleman disease doesn't respond to IL-6
> blockade, which approved drug should be tested next?
> Here's a run in the terminal. A director agent hands work to six sub-agents: literature, insight,
> planner, runner, analysis and safety. They pass ids, never pasted text. Every hypothesis is
> labelled agent-generated.
> Here's the ledger: evidence, hypotheses, experiments, results and verdicts, each validated and
> recorded.
> At the end, a safety agent compiles the ranking and publishing needs human approval.
> This demo run uses synthetic toy data, and the page says so. It shows the loop works. It is not
> a finding. Our real-data numbers are on the technical walkthrough.

**Technical walkthrough**
> Four layers. LLM agents read evidence and propose hypotheses, but never produce rankings. Python
> tools score drugs. A policy layer allows or denies every tool call. An append-only ledger
> validates every object.
> To stop the backtest cheating, the target drug's rank lives in an evaluation-only file no agent
> can read, and drugs are masked ids.
> Our drug pool is 1,146 approved parent molecules from ChEMBL 19. Targets are matched by UniProt
> accession, never by name, because one ChEMBL target is mislabelled but carries the mTOR accession.
> We pre-registered two analyses. On real data, with curated links, sirolimus lands in a tie group
> at mid-rank [8.5]. With activity data added, it ranks first [1].
> Limits: our enrichment method fails its own negative control, only method A has a real loader,
> and the LLM-only baseline isn't done.

## Appendix B: form text

**Tagline.** An agentic lab that replays a known drug discovery with the literature clock set back
to 2015, then measures how quickly it ranks the drug that was later proven.

**Short description.** Drug Repurposing Lab replays a real discovery as a backtest. With evidence
cut off at 1 January 2015, an agent loop ranks approved drugs for idiopathic multicentric Castleman
disease patients who don't respond to IL-6 blockade. We then measure how fast it ranks sirolimus,
the drug later shown to help. The target's rank is hidden from every agent.

**Tech stack.** Omnigent, Claude models via the Anthropic API, Python, ChEMBL 19, MSigDB v4.0,
Europe PMC, a JSON schema contract layer, and a static HTML dashboard.

**Challenges.** Keeping a backtest honest was the hardest part. The target drug's rank had to be
invisible to every agent, drugs had to be masked, and every data source had to be pinned before
the cutoff. One ChEMBL target is mislabelled but carries the mTOR accession, so we match by UniProt
accession, never by name. Our enrichment method also fails its own negative control, and the
ranking step did not exclude results from it. Running the loop showed this: on a cheaper model, our
safety agent withheld publication, which is the behavior we want, and it exposed the gap. We report
it as a limitation.

**Limitations to state.** Only method A has a real loader and it fails its own control. The curated
analysis produces a tie group. The LLM-only baseline, secondary metric and real multi-agent runs on
real data are not finished. Output is agent-generated hypotheses, not medical advice, and needs
laboratory and clinical validation.

## Final checklist (if the deadline has not passed)

- [ ] Merge the decision-record branch. Ask Sal to merge PR #31, or do not claim real-mode scoring.
- [ ] Record the three videos, then upload them and the team photo.
- [ ] Submit on the platform (draft first), then the Google Form.
- [ ] Be done by 14:30, since the 15 minute grace period is a safety net.

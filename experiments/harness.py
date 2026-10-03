"""Run the lab pipeline and its baselines headless and log target ranks to the eval-only file.

Every arm uses the lab's own tools, budget (tools.BUDGET_TOTAL) and data (lab.scoring), so the
same code runs in toy mode now and in real mode once the loaders are wired. Nothing here reads
toy data or branches on the mode: the mode only selects experiments/config/<mode>.json.

Arms
- agent:        the pipeline, LLM-free. Thompson planner (tools.planner_select_arms), and a
                reopen step that proposes the next configured hypothesis after a contested
                verdict, standing in for the insight agent.
- random:       the same pipeline with the planner replaced by a uniformly random arm order.
- no_reopen:    the agent pipeline without the reopen step.
- cooccurrence: one literature co-occurrence ranking, no experiments.
- agent_omnigent: optional, ledgers from real Omnigent runs, replayed the same way.

After each experiment the harness rebuilds the ranking the lab would publish at that point
(scoring.borda over results with a supported verdict whose hypothesis is still active, as
tools.compile_final_ranking does) and writes the target's mid-rank to the eval-only file.
Metrics (experiments/metrics.py) read only those rows.
"""
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

import numpy as np

import lab
from lab import CUTOFF_YEAR, ledger, scoring, tools

CONFIG_DIR = Path(__file__).resolve().parent / "config"
LAB_ARMS = {
    "agent": {"policy": "thompson", "reopen": True},
    "random": {"policy": "random", "reopen": True},
    "no_reopen": {"policy": "thompson", "reopen": False},
}
COOCCURRENCE = "cooccurrence"
IMPORTED = "agent_omnigent"
MAX_ROUNDS = 1000  # safety net; runs stop on budget or when no untested arm remains


def load_config(mode: str | None = None) -> dict:
    """The run configuration for the lab mode (toy or real)."""
    return json.loads((CONFIG_DIR / f"{mode or lab.MODE}.json").read_text())


@contextmanager
def run_context(run_dir: Path, seed: int, fresh: bool = True):
    """Point the ledger at run_dir and fix the planner and tie-break seeds for one run."""
    saved = (ledger.RUNTIME, tools._rng, os.environ.get("LAB_SEED"))
    ledger.RUNTIME = Path(run_dir)
    if fresh:
        ledger.reset()
    tools._rng = np.random.default_rng(seed)
    os.environ["LAB_SEED"] = str(seed)
    try:
        yield
    finally:
        ledger.RUNTIME, tools._rng = saved[0], saved[1]
        if saved[2] is None:
            os.environ.pop("LAB_SEED", None)
        else:
            os.environ["LAB_SEED"] = saved[2]


def _write_hypothesis(spec: dict, evidence_ids: list[str], parent_id: str | None = None) -> str:
    gene_set_ids = tools.find_gene_set(spec["term"], CUTOFF_YEAR)["gene_set_ids"]
    return tools.write_ledger("hypothesis", {
        "claim": spec["claim"], "evidence_ids": evidence_ids, "confidence": spec["confidence"],
        "status": "active", "gene_set_ids": gene_set_ids,
        "predicted_direction": spec["predicted_direction"], "parent_id": parent_id},
        agent="insight")["id"]


def _random_round(k: int, rng: np.random.Generator) -> list[str]:
    """Planner stand-in: untested arms in uniformly random order, same budget and rules."""
    left = tools.BUDGET_TOTAL - ledger.spent()
    arms = ledger.active_arms()
    chosen, spend, used_hyps = [], 0.0, set()
    for i in rng.permutation(len(arms)):
        arm = arms[i]
        if len(chosen) == k:
            break
        if arm["hyp_id"] in used_hyps or spend + arm["cost"] > left:
            continue
        chosen.append(arm)
        spend += arm["cost"]
        used_hyps.add(arm["hyp_id"])
    return [tools.write_ledger("experiment_spec", {
        "hyp_id": a["hyp_id"], "method": a["method"], "arm_id": a["arm_id"],
        "params": a["params"], "expected_cost": a["cost"],
        "expected_learning": round(a["mean_reward"], 4), "feasibility": a["feasibility"],
        "status": "planned", "seed": scoring.seed(), "control": a["control"]},
        agent="planner")["id"] for a in chosen]


def replay_into_eval(arm: str, seed: int) -> int:
    """Write the target's mid-rank after every experiment of the current ledger.

    Step 0 is before any experiment (every drug tied). Returns the number of experiments.
    Reads the ledger as the harness, never through an agent tool.
    """
    target = scoring.target_drug_id()
    if target is None:
        raise ValueError("no target drug: set LAB_TARGET_DRUG to its masked id")
    pool_size = len(scoring.masked_drug_pool(CUTOFF_YEAR))
    tie_seed = scoring.seed()
    conf: dict[str, float] = {}
    status: dict[str, str] = {}
    results: dict[str, list[dict]] = {}
    supported: list[tuple[str, str]] = []

    def emit(step: int) -> None:
        used = [(results[r], conf[h]) for r, h in supported if status.get(h) == "active"]
        ranked = scoring.borda(used, tie_seed) if used else []
        ledger.write_eval_only(f"{arm}/seed{seed}/step{step:03d}", {
            "arm": arm, "seed": seed, "step": step,
            "target_drug_rank": scoring.target_mid_rank(ranked, target, pool_size)})

    step = 0
    emit(0)
    for row in ledger._rows():
        kind, payload = row["kind"], row["payload"]
        if kind == "result":
            if step:
                emit(step)
            step += 1
            results[row["id"]] = payload["ranked_drugs"]
        elif kind == "hypothesis":
            conf[row["id"]], status[row["id"]] = payload["confidence"], payload["status"]
        elif kind == "hypothesis_update":
            status[payload["hyp_id"]] = payload["status"]
            conf[payload["hyp_id"]] = payload.get("confidence", conf.get(payload["hyp_id"]))
        elif kind == "verdict" and payload["verdict"] == "supported":
            supported.append((payload["res_id"], payload["hyp_id"]))
    if step:
        emit(step)
    return step


def run_pipeline(run_dir: Path, arm: str, seed: int, config: dict) -> dict:
    """One headless run of a lab arm until the budget is spent or no untested arm remains."""
    policy, reopen = LAB_ARMS[arm]["policy"], LAB_ARMS[arm]["reopen"]
    with run_context(run_dir, seed):
        evidence = tools.search_literature(config["query"], CUTOFF_YEAR)["evidence_ids"]
        for spec in config["initial"]:
            _write_hypothesis(spec, evidence)
        pending = list(config.get("reopen", []))
        rng = np.random.default_rng(seed)
        reopened = 0
        for _ in range(MAX_ROUNDS):
            if policy == "thompson":
                exp_ids = tools.planner_select_arms(config["k"])["exp_ids"]
            else:
                exp_ids = _random_round(config["k"], rng)
            if not exp_ids:
                break
            for exp_id in exp_ids:
                an = tools.analyze_result(tools.run_experiment(exp_id)["res_id"])
                if reopen and an.get("verdict") == "contested" and pending:
                    _write_hypothesis(pending.pop(0), evidence, parent_id=an["hyp_id"])
                    reopened += 1
        experiments = replay_into_eval(arm, seed)
        return {"arm": arm, "seed": seed, "experiments": experiments,
                "spent": ledger.spent(), "reopened": reopened}


def run_cooccurrence(run_dir: Path, seed: int) -> dict:
    """The literature co-occurrence ranking: no experiments, so one constant row."""
    with run_context(run_dir, seed):
        target = scoring.target_drug_id()
        if target is None:
            raise ValueError("no target drug: set LAB_TARGET_DRUG to its masked id")
        pool = scoring.masked_drug_pool(CUTOFF_YEAR)
        ranked = scoring.literature_cooccurrence(pool, CUTOFF_YEAR, seed)
        ledger.write_eval_only(f"{COOCCURRENCE}/seed{seed}/step000", {
            "arm": COOCCURRENCE, "seed": seed, "step": 0, "constant": True,
            "target_drug_rank": scoring.target_mid_rank(ranked, target, len(pool))})
        return {"arm": COOCCURRENCE, "seed": seed, "experiments": 0, "spent": 0.0}


def import_agent_run(run_dir: Path, source_ledger_dir: Path, index: int) -> dict:
    """Replay a real Omnigent run's ledger (copied, never modified) as the agent_omnigent arm."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(source_ledger_dir) / "ledger.jsonl", run_dir / "ledger.jsonl")
    seeds = [r["payload"]["seed"] for r in _read_rows(run_dir / "ledger.jsonl")
             if r["kind"] == "result"]
    with run_context(run_dir, seeds[0] if seeds else 0, fresh=False):
        experiments = replay_into_eval(IMPORTED, index)
        return {"arm": IMPORTED, "seed": index, "experiments": experiments,
                "spent": ledger.spent()}


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_all(out_dir: Path, seeds: list[int], arms: list[str], config: dict,
            agent_ledgers: list[Path] = ()) -> list[dict]:
    """Run every requested arm for every seed into out_dir/runs/<arm>/seed_<n>."""
    runs = Path(out_dir) / "runs"
    if runs.exists():
        shutil.rmtree(runs)  # never mix eval rows from an earlier evaluation
    summaries = []
    for arm in arms:
        for seed in seeds:
            run_dir = runs / arm / f"seed_{seed:03d}"
            if arm == COOCCURRENCE:
                summaries.append(run_cooccurrence(run_dir, seed))
            else:
                summaries.append(run_pipeline(run_dir, arm, seed, config))
    for i, source in enumerate(agent_ledgers):
        summaries.append(import_agent_run(runs / IMPORTED / f"run_{i:03d}", Path(source), i))
    return summaries

"""Evaluation harness: arms, eval-only metrics, table and plot."""
import ast
import json
import shutil
from pathlib import Path

import pytest

from experiments import evaluate, harness, metrics
from lab import ledger, scoring, tools

SEEDS = 3
ARMS = {"agent", "random", "no_reopen", "cooccurrence"}


@pytest.fixture(scope="module")
def evaluation(tmp_path_factory):
    out = tmp_path_factory.mktemp("eval")
    result = evaluate.main(["--seeds", str(SEEDS), "--out", str(out)])
    return out, result


def _ledger_rows(run_dir: Path) -> list[dict]:
    path = run_dir / "ledger.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _run_dirs(out: Path, arm: str) -> list[Path]:
    return sorted((out / "runs" / arm).iterdir())


# ---------- outputs ----------

def test_writes_table_and_plot_for_every_arm(evaluation):
    out, result = evaluation
    assert {s["arm"] for s in result["summary"]} == ARMS
    assert all(s["runs"] == SEEDS for s in result["summary"])
    for path in (result["csv"], result["md"], result["png"]):
        assert Path(path).exists() and Path(path).stat().st_size > 0
    md = Path(result["md"]).read_text()
    assert "Experiments to top 10" in md and "Final mid-rank" in md
    assert Path(result["png"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_metrics_use_only_the_eval_only_files(evaluation, tmp_path):
    out, result = evaluation
    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    for path in (copy / "runs").rglob("ledger.jsonl"):
        path.unlink()  # metrics must not need the ledger
    again = metrics.summarize(metrics.load_eval_rows(copy))
    assert json.dumps(again, sort_keys=True) == json.dumps(result["summary"], sort_keys=True)
    tree = ast.parse(Path(metrics.__file__).read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {m for m in imported if m == "lab" or m.startswith(("lab.", "experiments"))}


# ---------- same budget and data as the lab ----------

def test_every_lab_arm_stays_within_the_lab_budget(evaluation):
    out, _ = evaluation
    for arm in harness.LAB_ARMS:
        for run_dir in _run_dirs(out, arm):
            rows = _ledger_rows(run_dir)
            spent = sum(r["payload"]["cost"] for r in rows if r["kind"] == "result")
            assert 0 < spent <= tools.BUDGET_TOTAL
            steps = [json.loads(x)["step"] for x in (run_dir / "eval_only.jsonl").read_text()
                     .splitlines() if "step" in json.loads(x)]
            assert steps == list(range(sum(r["kind"] == "result" for r in rows) + 1))


def test_replayed_final_rank_matches_the_compiled_final_ranking(evaluation, tmp_path):
    out, _ = evaluation
    for arm in harness.LAB_ARMS:
        for i, run_dir in enumerate(_run_dirs(out, arm)):
            copy = tmp_path / arm / run_dir.name
            shutil.copytree(run_dir, copy)
            evals = [json.loads(x) for x in (copy / "eval_only.jsonl").read_text().splitlines()]
            last = max((e for e in evals if "step" in e), key=lambda e: e["step"])
            with harness.run_context(copy, i, fresh=False):
                try:
                    fin = ledger.get(tools.compile_final_ranking()["final_ranking_id"])
                    expected = scoring.target_mid_rank(fin["ranked_drugs"], "d042", 60)
                except ValueError:  # nothing supported: every drug tied
                    expected = (60 + 1) / 2
            assert last["target_drug_rank"] == expected, (arm, run_dir.name)


# ---------- arms ----------

def test_only_reopen_arms_propose_revised_hypotheses(evaluation):
    out, _ = evaluation
    for arm in harness.LAB_ARMS:
        revised = [any(r["kind"] == "hypothesis" and r["payload"].get("parent_id")
                       for r in _ledger_rows(d)) for d in _run_dirs(out, arm)]
        if harness.LAB_ARMS[arm]["reopen"]:
            assert any(revised), arm  # the toy IL-6/unmapped hypotheses get contested
        else:
            assert not any(revised), arm


def test_random_arm_order_depends_on_the_seed_and_is_reproducible(tmp_path):
    config = harness.load_config("toy")
    orders = []
    for seed in (0, 1, 2, 0):
        run_dir = tmp_path / f"r{len(orders)}"
        harness.run_pipeline(run_dir, "random", seed, config)
        orders.append([r["payload"]["arm_id"] for r in _ledger_rows(run_dir)
                       if r["kind"] == "experiment_spec"])
    assert orders[0] == orders[3]
    assert len({tuple(o) for o in orders[:3]}) > 1


def test_cooccurrence_baseline_is_one_constant_ranking(evaluation):
    out, _ = evaluation
    for run_dir in _run_dirs(out, "cooccurrence"):
        rows = [json.loads(x) for x in (run_dir / "eval_only.jsonl").read_text().splitlines()]
        assert len(rows) == 1 and rows[0]["constant"] and rows[0]["step"] == 0
    pool = scoring.masked_drug_pool(2015)
    top5 = {r["drug_id"] for r in scoring.literature_cooccurrence(pool, 2015, 0)[:5]}
    assert top5 == {"d001", "d002", "d003", "d004", "d005"}  # the famous IL-6 decoys


def test_real_agent_runs_can_be_imported_without_touching_the_source(evaluation, tmp_path):
    out, _ = evaluation
    source = tmp_path / "omnigent_runtime"
    shutil.copytree(_run_dirs(out, "agent")[0], source)
    (source / "eval_only.jsonl").unlink()
    before = (source / "ledger.jsonl").read_bytes()
    target = tmp_path / "with_agent"
    harness.run_all(target, [0], ["cooccurrence"], harness.load_config("toy"), [source])
    traj = metrics.trajectories(metrics.load_eval_rows(target))
    original = metrics.trajectories(metrics.load_eval_rows(out))["agent"][0]
    assert traj["agent_omnigent"][0]["ranks"] == original["ranks"]
    assert (source / "ledger.jsonl").read_bytes() == before
    assert not (source / "eval_only.jsonl").exists()


def test_missing_target_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(scoring, "target_drug_id", lambda: None)
    with pytest.raises(ValueError, match="LAB_TARGET_DRUG"):
        harness.run_pipeline(tmp_path / "x", "agent", 0, harness.load_config("toy"))


# ---------- metric definitions ----------

def _rows(arm, seed, ranks, constant=False):
    return [{"arm": arm, "seed": seed, "step": i, "target_drug_rank": r,
             **({"constant": True} if constant else {})} for i, r in enumerate(ranks)]


def test_experiments_to_top10_and_final_rank():
    rows = (_rows("agent", 0, [30.5, 20, 9.5, 12]) + _rows("agent", 1, [30.5, 15, 14])
            + _rows("agent", 2, [30.5, 10, 3]) + _rows("cooccurrence", 0, [8], constant=True))
    traj = metrics.trajectories(rows)
    assert [metrics.experiments_to_top(traj["agent"][s]) for s in (0, 1, 2)] == [2, None, 1]
    assert metrics.experiments_to_top(traj["cooccurrence"][0]) == 0
    agent = next(s for s in metrics.summarize(rows) if s["arm"] == "agent")
    assert agent["reached_top10"] == pytest.approx(2 / 3)
    assert agent["exp_to_top10_median"] == 1.5
    assert agent["final_midrank_median"] == 12 and agent["final_midrank_best"] == 3


def test_finished_runs_carry_their_final_rank_forward():
    traj = metrics.trajectories(_rows("agent", 0, [30.5, 5]) + _rows("agent", 1, [30.5, 20, 9]))
    m = metrics.rank_matrix(traj["agent"], 3)
    assert m.tolist() == [[30.5, 5, 5, 5], [30.5, 20, 9, 9]]


def test_target_mid_rank_ties_unranked_drugs():
    assert scoring.target_mid_rank([], "d042", 60) == 30.5
    ranked = [{"drug_id": "d001", "score": 2.0, "rank": 1}]
    assert scoring.target_mid_rank(ranked, "d042", 60) == 1 + 60 / 2


# ---------- toy now, real later ----------

def test_harness_code_never_touches_toy_data_or_the_mode():
    for module in (harness, metrics, evaluate):
        source = Path(module.__file__).read_text()
        assert "toy_data" not in source and "MODE ==" not in source and '"toy"' not in source
    toy, real = harness.load_config("toy"), harness.load_config("real")
    assert set(toy) == set(real)
    assert {h["term"] for h in toy["initial"]} != {h["term"] for h in real["initial"]}

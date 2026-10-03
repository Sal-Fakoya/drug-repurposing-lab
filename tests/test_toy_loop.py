import json

from scripts_path import run_loop

from lab import ledger, tools


def test_loop_respects_budget_and_writes_valid_rows():
    out = run_loop(rounds=20, k=2, verbose=False)
    assert 0 < out["spent"] <= tools.BUDGET_TOTAL
    assert all(row["payload"] for row in ledger.rows_of_kind("result"))


def test_null_hypothesis_gets_contested():
    run_loop(rounds=20, k=2, verbose=False)
    statuses = {h["claim"]: h["status"] for h in ledger.hypotheses()}
    assert statuses["Unmapped mechanism"] == "contested"


def test_target_rank_never_appears_in_agent_facing_output():
    ev = tools.search_literature("q", 2013)["evidence_ids"]
    gs = tools.find_gene_set("mtor", 2013)["gene_set_ids"]
    hid = tools.write_ledger("hypothesis", {
        "claim": "m", "evidence_ids": ev, "confidence": 0.5, "label": "agent-generated",
        "status": "active", "gene_set_ids": gs, "predicted_direction": "enriched"},
        agent="insight")["id"]
    sel = tools.planner_select_arms(2)
    run = tools.run_experiment(sel["exp_ids"][0])
    an = tools.analyze_result(run["res_id"])
    seen = [sel, run, an, tools.read_ledger([hid, sel["exp_ids"][0], run["res_id"]])]
    assert "target_drug_rank" not in json.dumps(seen)
    assert ledger.read_eval_only(run["res_id"]) is not None  # but the harness can read it


def test_run_experiment_output_has_no_drug_names():
    ev = tools.search_literature("q", 2013)["evidence_ids"]
    tools.write_ledger("hypothesis", {
        "claim": "m", "evidence_ids": ev, "confidence": 0.5, "label": "agent-generated",
        "status": "active", "gene_set_ids": ["GS_MTOR"], "predicted_direction": "enriched"},
        agent="insight")
    run = tools.run_experiment(tools.planner_select_arms(1)["exp_ids"][0])
    assert all(i.startswith("d") and i[1:].isdigit() for i in run["top_ids"])


def test_literature_tool_enforces_cutoff():
    import pytest
    with pytest.raises(ValueError):
        tools.search_literature("q", 2020)


def test_same_seed_gives_same_arm_choices(monkeypatch):
    import numpy as np
    picks = []
    for _ in range(2):
        ledger.reset()
        monkeypatch.setattr(tools, "_rng", np.random.default_rng(0))
        ev = tools.search_literature("q", 2013)["evidence_ids"]
        for term in ("il-6", "mtor", "jak"):
            tools.write_ledger("hypothesis", {
                "claim": term, "evidence_ids": ev, "confidence": 0.5,
                "label": "agent-generated", "status": "active",
                "gene_set_ids": tools.find_gene_set(term, 2013)["gene_set_ids"],
                "predicted_direction": "enriched"}, agent="insight")
        picks.append(tools.planner_select_arms(2)["arm_ids"])
    assert picks[0] == picks[1]


def test_no_arm_is_run_twice():
    run_loop(rounds=20, k=2, verbose=False)
    arms = [ledger.get(r["id"])["arm_id"] for r in ledger.rows_of_kind("experiment_spec")]
    assert len(arms) == len(set(arms))

"""One or more tests per bug found by the toy pipeline test (see the PR description)."""
import math

import pytest
from scripts_path import run_loop

import lab
from lab import ledger, scoring, tools, toy_data


def _hyp(gene_set_ids, direction="enriched", confidence=0.5, **extra) -> str:
    ev = tools.search_literature("q", 2015)["evidence_ids"]
    return tools.write_ledger("hypothesis", {
        "claim": f"{gene_set_ids} {direction}", "evidence_ids": ev, "confidence": confidence,
        "status": "active", "gene_set_ids": gene_set_ids, "predicted_direction": direction,
        **extra}, agent="insight")["id"]


def _spec(hyp_id, method="A", gene_set_ids=None, cost=1.0, **extra) -> str:
    gene_set_ids = gene_set_ids or ledger.get(hyp_id)["gene_set_ids"]
    return tools.write_ledger("experiment_spec", {
        "hyp_id": hyp_id, "method": method, "arm_id": f"{hyp_id}:{method}",
        "params": {"gene_set_ids": gene_set_ids}, "expected_cost": cost,
        "expected_learning": 1.0, "feasibility": 1.0, **extra}, agent="planner")["id"]


def _run_and_analyze(exp_id) -> dict:
    return tools.analyze_result(tools.run_experiment(exp_id)["res_id"])


# ---------- 1. confidence follows each hypothesis's own predicted direction ----------

def test_same_result_supports_enriched_and_contests_not_enriched_prediction():
    up = _hyp(["GS_MTOR"], "enriched")
    down = _hyp(["GS_MTOR"], "not_enriched")
    a = _run_and_analyze(_spec(up))
    b = _run_and_analyze(_spec(down))
    assert a["z"] == b["z"] > scoring.Z_ENRICHED  # same measurement
    assert a["verdict"] == "supported" and a["new_confidence"] > 0.5
    assert b["verdict"] == "contested" and b["new_confidence"] < 0.5


def test_not_enriched_prediction_is_supported_by_absent_enrichment():
    verdict, new = scoring.assess(0.0, "not_enriched", 0.4)
    assert verdict == "supported" and new > 0.4
    with pytest.raises(ValueError):
        scoring.assess(1.0, "up", 0.4)


# ---------- 2. hypotheses must name gene sets and direction, or be untestable ----------

def test_testable_hypothesis_without_direction_or_gene_sets_is_rejected():
    for missing in ({"predicted_direction": None}, {"gene_set_ids": []}):
        payload = {"claim": "c", "evidence_ids": ["ev_001"], "confidence": 0.5,
                   "status": "active", "gene_set_ids": ["GS_IL6"],
                   "predicted_direction": "enriched", **missing}
        payload = {k: v for k, v in payload.items() if v is not None}
        with pytest.raises(ValueError):
            tools.write_ledger("hypothesis", payload, agent="insight")


def test_untestable_hypothesis_is_accepted_and_never_planned():
    hid = tools.write_ledger("hypothesis", {
        "claim": "immune dysregulation, not a pathway", "evidence_ids": ["ev_001"],
        "confidence": 0.5, "status": "active", "gene_set_ids": [], "testable": False},
        agent="insight")["id"]
    assert all(a["hyp_id"] != hid for a in ledger.active_arms())


# ---------- 3. a run design is never selected again ----------

def test_planner_never_reselects_a_design_that_was_run_under_another_arm_id():
    hid = _hyp(["GS_MTOR"])
    exp = tools.write_ledger("experiment_spec", {  # same design, different arm id
        "hyp_id": hid, "method": "A", "arm_id": "manual-override",
        "params": {"gene_set_ids": ["GS_MTOR"]}, "expected_cost": 1.0,
        "expected_learning": 1.0, "feasibility": 1.0}, agent="planner")["id"]
    tools.run_experiment(exp)
    assert ledger.arm_stats().get(f"{hid}:A") is None  # not analysed, so n is still 0
    offered = {(a["hyp_id"], a["method"]) for a in ledger.active_arms()}
    assert (hid, "A") not in offered and (hid, "B") in offered
    picked = tools.planner_select_arms(5)["arm_ids"]
    assert f"{hid}:A" not in picked
    with pytest.raises(ValueError):
        _spec(hid, "A")


# ---------- 4. run_experiment uses and records the spec's seed ----------

def test_run_experiment_uses_and_records_the_spec_seed():
    hid = _hyp(["GS_IL6"])
    exp = _spec(hid, "B", seed=7)
    res = ledger.get(tools.run_experiment(exp)["res_id"])
    assert res["seed"] == 7
    pool = scoring.masked_drug_pool(2015)
    assert res["ranked_drugs"] == scoring.literature_graph(pool, ["GS_IL6"], 2015, seed=7)


def test_planner_writes_a_seed_into_each_spec(monkeypatch):
    monkeypatch.setenv("LAB_SEED", "11")
    _hyp(["GS_IL6"])
    exp = tools.planner_select_arms(1)["exp_ids"][0]
    assert ledger.get(exp)["seed"] == 11


# ---------- 5. combined gene sets get a real z ----------

def _union_z(ranked, gene_set_ids, k=10):
    """The old statistic: a drug is a hit if it targets ANY of the gene sets."""
    pool = scoring.masked_drug_pool(2015)
    genes = scoring._gene_union(gene_set_ids)
    hit = {p["drug_id"] for p in pool if genes & set(p["targets"])}
    n, big_k = len(pool), len(hit)
    observed = sum(1 for r in ranked[:k] if r["drug_id"] in hit)
    var = k * (big_k / n) * (1 - big_k / n) * (n - k) / (n - 1)
    return (observed - k * big_k / n) / math.sqrt(var)


@pytest.mark.parametrize("method", ["A", "B"])
def test_combined_gene_set_z_is_the_stouffer_combination_of_per_set_z(method):
    pool = scoring.masked_drug_pool(2015)
    score = scoring.pathway_enrichment if method == "A" else scoring.literature_graph
    ranked = score(pool, ["GS_IL6", "GS_MTOR"], 2015, seed=0)
    z1 = scoring.enrichment_z(ranked, ["GS_IL6"])
    z2 = scoring.enrichment_z(ranked, ["GS_MTOR"])
    combined = scoring.enrichment_z(ranked, ["GS_IL6", "GS_MTOR"])
    assert math.isclose(combined, (z1 + z2) / math.sqrt(2))
    assert not math.isclose(combined, _union_z(ranked, ["GS_IL6", "GS_MTOR"]))


def test_combined_gene_set_z_reports_what_the_union_test_hid():
    pool = scoring.masked_drug_pool(2015)
    b = scoring.literature_graph(pool, ["GS_IL6", "GS_MTOR"], 2015, seed=0)
    assert _union_z(b, ["GS_IL6", "GS_MTOR"]) == 0.0  # the reported bug
    # The IL-6 decoys dominate the summed co-mention ranking, so mTOR is under-represented.
    assert scoring.enrichment_z(b, ["GS_MTOR"]) < 0 < scoring.enrichment_z(b, ["GS_IL6"])
    a = scoring.pathway_enrichment(pool, ["GS_IL6", "GS_MTOR"], 2015, seed=0)
    assert scoring.enrichment_z(a, ["GS_IL6", "GS_MTOR"]) > scoring.Z_ENRICHED


# ---------- 6. one update, to the named hypothesis, once per result and per design ----------

def test_result_updates_only_its_own_hypothesis_once():
    target = _hyp(["GS_MTOR"], confidence=0.5)
    bystander = _hyp(["GS_IL6"], confidence=0.6)
    res_id = tools.run_experiment(_spec(target))["res_id"]
    first = tools.analyze_result(res_id)
    again = tools.analyze_result(res_id)
    assert again["new_confidence"] == first["new_confidence"]
    updates = ledger.rows_of_kind("hypothesis_update")
    assert [u["payload"]["hyp_id"] for u in updates] == [target]
    assert len(ledger.rows_of_kind("verdict")) == 1
    assert ledger.get(bystander)["confidence"] == 0.6


def test_a_repeated_design_cannot_raise_confidence_twice():
    hid = _hyp(["GS_MTOR"], confidence=0.5)
    exp = _spec(hid)
    first = _run_and_analyze(exp)
    # Force a second result of the same design past the tool guards.
    twin_spec = ledger.append("experiment_spec", {**{k: v for k, v in ledger.get(exp).items()
                                                     if k not in ("id", "kind")},
                                                  "status": "planned"}, agent="planner")
    payload = {k: v for k, v in ledger.get(first["res_id"]).items() if k not in ("id", "kind")}
    twin = ledger.append("result", {**payload, "exp_id": twin_spec}, agent="runner")
    out = tools.analyze_result(twin)
    assert out["duplicate_design"] is True
    assert len(ledger.rows_of_kind("hypothesis_update")) == 1
    assert ledger.get(hid)["confidence"] == first["new_confidence"]


def test_agents_cannot_raise_confidence_through_write_ledger():
    hid = _hyp(["GS_MTOR"], confidence=0.5)
    with pytest.raises(ValueError):
        tools.write_ledger("hypothesis_update", {"hyp_id": hid, "status": "active",
                                                 "confidence": 0.9}, agent="insight")
    tools.write_ledger("hypothesis_update", {"hyp_id": hid, "status": "contested",
                                             "confidence": 0.3}, agent="insight")
    assert ledger.get(hid)["confidence"] == 0.3


# ---------- 7. budget is charged when an experiment runs ----------

def test_budget_is_charged_at_run_not_at_planning(monkeypatch):
    monkeypatch.setattr(tools, "BUDGET_TOTAL", 3.0)
    _hyp(["GS_MTOR"])
    sel = tools.planner_select_arms(2)
    assert ledger.spent() == 0 and sel["budget_left"] == 3.0 and sel["planned_cost"] > 0
    first, second = sel["exp_ids"]
    tools.run_experiment(first)
    assert ledger.spent() == ledger.get(first)["expected_cost"]
    monkeypatch.setattr(tools, "BUDGET_TOTAL", ledger.spent() + 0.5)
    with pytest.raises(ValueError, match="budget"):
        tools.run_experiment(second)


def test_running_a_spec_twice_returns_the_same_result_and_charges_once():
    hid = _hyp(["GS_MTOR"])
    exp = _spec(hid)
    a, b = tools.run_experiment(exp), tools.run_experiment(exp)
    assert a["res_id"] == b["res_id"] and b["already_run"] is True
    assert ledger.spent() == 1.0


# ---------- 8. stop when the budget is spent or no untested arm remains ----------

def test_loop_stops_only_when_no_untested_arm_remains_or_budget_is_spent():
    out = run_loop(rounds=100, k=2, verbose=False)
    assert out["stop_reason"] in {"no untested arm remains", "budget spent"}
    if out["stop_reason"] == "no untested arm remains":
        assert ledger.active_arms() == []
    final = tools.planner_select_arms(2)
    assert final["stop"] is True and final["exp_ids"] == []


# ---------- 9. negative-control gene set ----------

def test_negative_control_is_fixed_and_offered_to_the_planner():
    assert toy_data.GENE_SETS[toy_data.NEGATIVE_CONTROL] == [
        "g02", "g07", "g08", "g10", "g17", "g24", "g32", "g33"]
    assert ledger.active_arms() == []  # nothing to control for without a hypothesis
    _hyp(["GS_IL6"])
    controls = [a for a in ledger.active_arms() if a["control"]]
    assert {a["method"] for a in controls} == {"A", "B"}
    assert all(a["params"] == {"gene_set_ids": [toy_data.NEGATIVE_CONTROL]} for a in controls)


def test_negative_control_result_updates_no_hypothesis():
    _hyp(["GS_IL6"])
    sel = tools.planner_select_arms(3)
    ctrl = next(e for e in sel["exp_ids"] if ledger.get(e)["control"])
    out = _run_and_analyze(ctrl)
    assert out["control"] is True and "control_passed" in out
    assert ledger.rows_of_kind("hypothesis_update") == []
    assert ledger.rows_of_kind("verdict") == []


def test_adding_the_control_did_not_change_existing_toy_data():
    _, comentions = toy_data.build()
    assert comentions[("d001", "GS_IL6")] >= 12 and comentions[("d042", "GS_MTOR")] >= 2
    assert all((d, toy_data.NEGATIVE_CONTROL) in comentions for d in toy_data.build()[0])


# ---------- 10. the planner never sees result rows ----------

def test_planner_view_hides_results_and_evidence_but_shows_arm_stats():
    hid = _hyp(["GS_MTOR"])
    exp = _spec(hid)
    res = tools.run_experiment(exp)["res_id"]
    an = tools.analyze_result(res)
    ev = ledger.get(hid)["evidence_ids"][0]
    view = tools.read_planner_ledger([hid, exp, an["verdict_id"], res, ev])
    kinds = {r["id"]: r for r in view["rows"]}
    assert kinds[hid]["kind"] == "hypothesis" and "claim" in kinds[hid]
    assert "params" in kinds[exp] and "verdict" in kinds[an["verdict_id"]]
    assert "ranked_drugs" not in kinds[res] and "error" in kinds[res]
    assert "snippet" not in kinds[ev] and "error" in kinds[ev]
    assert f"{hid}:A" in view["arm_stats"]


# ---------- 11. synthetic flag on ledger rows ----------

def test_rows_are_flagged_synthetic_in_toy_mode_only(monkeypatch):
    hid = _hyp(["GS_IL6"])
    assert ledger._find(hid)["synthetic"] is True
    monkeypatch.setattr(lab, "MODE", "real")
    real = ledger.append("approval", {"res_id": "x", "decision": "refused"}, agent="safety")
    assert ledger._find(real)["synthetic"] is False
    assert "synthetic" not in ledger._find(real)["labels"]


# ---------- 12. experiment spec status ----------

def test_spec_status_goes_planned_run_and_unrun_specs_get_superseded():
    _hyp(["GS_IL6"])
    _hyp(["GS_MTOR"])
    first = tools.planner_select_arms(2)["exp_ids"]
    assert {ledger.get(e)["status"] for e in first} == {"planned"}
    tools.run_experiment(first[0])
    assert ledger.get(first[0])["status"] == "run"
    tools.planner_select_arms(2)  # replanning supersedes the spec that was never run
    assert ledger.get(first[1])["status"] == "superseded"
    with pytest.raises(ValueError, match="superseded"):
        tools.run_experiment(first[1])


# ---------- 13. final ranking record, reviewed and published ----------

def test_final_ranking_uses_only_supported_results_and_gates_publication():
    run_loop(verbose=False)
    fin = ledger.get(ledger.rows_of_kind("final_ranking")[-1]["id"])
    supported = {r["payload"]["res_id"] for r in ledger.rows_of_kind("verdict")
                 if r["payload"]["verdict"] == "supported"}
    assert fin["res_ids"] and set(fin["res_ids"]) <= supported
    assert all(ledger.get(h)["status"] == "active" for h in fin["hyp_ids"])
    with pytest.raises(ValueError, match="safety_review"):
        tools.publish_final_ranking(fin["id"])
    with pytest.raises(ValueError, match="final_ranking"):
        tools.publish_final_ranking(fin["res_ids"][0])
    tools.write_ledger("safety_review", {"res_id": fin["id"], "final_ranking_id": fin["id"],
                                         "checks": {"cites_evidence": True}, "passed": True},
                       agent="safety")
    out = tools.publish_final_ranking(fin["id"])
    assert ledger.get(out["approval_id"])["final_ranking_id"] == fin["id"]
    assert (ledger.ROOT / out["published"]).exists()


def test_compile_final_ranking_refuses_without_supported_results():
    with pytest.raises(ValueError):
        tools.compile_final_ranking()


# ---------- 14. labels are added automatically ----------

def test_labels_come_from_kind_and_mode():
    hid = tools.write_ledger("hypothesis", {
        "claim": "c", "evidence_ids": ["ev_001"], "confidence": 0.5, "status": "active",
        "gene_set_ids": ["GS_IL6"], "predicted_direction": "enriched"}, agent="insight")["id"]
    assert ledger.get(hid)["label"] == "agent-generated"  # filled in, not supplied
    assert ledger._find(hid)["labels"] == ["agent-generated", "synthetic"]
    ev = tools.search_literature("q", 2015)["evidence_ids"][0]
    assert ledger._find(ev)["labels"] == ["synthetic"]


# ---------- 15. verdict and confidence change agree ----------

def test_verdicts_and_confidence_changes_always_agree():
    run_loop(verbose=False)
    verdicts = [r["payload"] for r in ledger.rows_of_kind("verdict")]
    assert verdicts
    for v in verdicts:
        upd = ledger._find(v["update_id"])["payload"]
        assert upd["confidence"] == v["new_confidence"]
        if v["verdict"] == "supported":
            assert v["new_confidence"] >= v["prior_confidence"]
        else:
            assert v["new_confidence"] <= v["prior_confidence"]


def test_agents_cannot_write_verdicts_or_other_tool_only_rows():
    for kind in tools.TOOL_ONLY_KINDS:
        with pytest.raises(ValueError, match="own tool"):
            tools.write_ledger(kind, {}, agent="analysis")


# ---------- 16. every tool-written row names its agent ----------

def test_no_tool_written_row_has_an_empty_agent():
    run_loop(verbose=False)
    fin = ledger.rows_of_kind("final_ranking")[-1]["id"]
    tools.write_ledger("safety_review", {"res_id": fin, "final_ranking_id": fin,
                                         "checks": {}, "passed": True}, agent="safety")
    tools.publish_final_ranking(fin)
    rows = ledger._rows()
    assert {r["kind"] for r in rows} >= {"evidence_record", "hypothesis", "experiment_spec",
                                         "result", "verdict", "hypothesis_update",
                                         "final_ranking", "safety_review", "approval"}
    assert all(r["agent"] in tools.AGENTS for r in rows), [
        (r["id"], r["agent"]) for r in rows if r["agent"] not in tools.AGENTS]
    expected = {"evidence_record": "literature", "result": "runner", "verdict": "analysis",
                "hypothesis_update": "analysis", "final_ranking": "safety"}
    for r in rows:
        if r["kind"] in expected:
            assert r["agent"] == expected[r["kind"]], r["id"]

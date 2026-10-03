import math

import numpy as np
import pytest

from lab import ledger, scoring, tools


def _hypothesis(term: str, confidence: float = 0.5, direction: str = "enriched") -> str:
    ev = tools.search_literature("q", 2013)["evidence_ids"]
    return tools.write_ledger("hypothesis", {
        "claim": term, "evidence_ids": ev, "confidence": confidence, "status": "active",
        "gene_set_ids": tools.find_gene_set(term, 2013)["gene_set_ids"],
        "predicted_direction": direction}, agent="insight")["id"]


def _plan_hypothesis_arm() -> str:
    """Plan one round and return the spec id of the hypothesis arm (not the control)."""
    for exp_id in tools.planner_select_arms(2)["exp_ids"]:
        if not ledger.get(exp_id).get("control"):
            return exp_id
    raise AssertionError("planner offered no hypothesis arm")


# ---------- (1) write_ledger stores the writing agent ----------

def test_write_ledger_stores_agent_on_the_row():
    ev = tools.search_literature("q", 2013)["evidence_ids"]
    hid = tools.write_ledger("hypothesis", {
        "claim": "c", "evidence_ids": ev, "confidence": 0.5, "label": "agent-generated",
        "status": "active", "gene_set_ids": ["GS_IL6"], "predicted_direction": "enriched"},
        agent="insight")["id"]
    assert ledger._find(hid)["agent"] == "insight"


@pytest.mark.parametrize("agent", [None, "", "director", "nobody"])
def test_write_ledger_requires_a_known_agent(agent):
    with pytest.raises((ValueError, TypeError)):
        tools.write_ledger("hypothesis", {
            "claim": "c", "evidence_ids": ["ev_001"], "confidence": 0.5, "status": "active",
            "gene_set_ids": ["GS_IL6"], "predicted_direction": "enriched"}, agent=agent)


# ---------- (2) planner: one arm per hypothesis per round, untried arms first ----------

@pytest.mark.parametrize("seed", range(10))
def test_planner_never_picks_two_arms_of_one_hypothesis(monkeypatch, seed):
    monkeypatch.setattr(tools, "_rng", np.random.default_rng(seed))
    for term in ("il-6", "mtor", "jak"):
        _hypothesis(term)
    sel = tools.planner_select_arms(5)
    hyps = [ledger.get(e)["hyp_id"] for e in sel["exp_ids"]]
    # three hypotheses plus the negative control, each at most once
    assert len(hyps) == 4 and len(set(hyps)) == 4


def test_planner_with_one_hypothesis_picks_one_arm_of_it():
    hid = _hypothesis("mtor")
    hyps = [ledger.get(e)["hyp_id"] for e in tools.planner_select_arms(3)["exp_ids"]]
    assert hyps.count(hid) == 1 and len(hyps) == len(set(hyps))


def test_planner_prefers_untried_arms(monkeypatch):
    monkeypatch.setattr(ledger, "MAX_RUNS_PER_ARM", 2)
    h1 = _hypothesis("il-6")
    _hypothesis("mtor")
    # A tried arm with a huge reward would win any Thompson draw against the n=0 prior.
    ledger.update_arm_stats(f"{h1}:A", "res_fake", 100.0)
    for seed in range(10):
        monkeypatch.setattr(tools, "_rng", np.random.default_rng(seed))
        sel = tools.planner_select_arms(1)
        assert sel["arm_ids"][0] != f"{h1}:A"


# ---------- (3) analyze_result persists confidence and later analyses build on it ----------

def test_analyze_result_persists_update_and_chains_confidence():
    hid = _hypothesis("mtor", confidence=0.5)

    first = tools.analyze_result(
        tools.run_experiment(_plan_hypothesis_arm())["res_id"])
    upd = ledger._find(first["update_id"])
    assert upd["kind"] == "hypothesis_update" and upd["parent_id"] == first["res_id"]
    assert upd["agent"] == "analysis"
    assert upd["payload"]["confidence"] == first["new_confidence"]
    assert ledger.get(hid)["confidence"] == first["new_confidence"]

    second = tools.analyze_result(
        tools.run_experiment(_plan_hypothesis_arm())["res_id"])
    assert second["prior_confidence"] == first["new_confidence"]
    _, expected = scoring.assess(second["z"], "enriched", first["new_confidence"])
    assert math.isclose(second["new_confidence"], expected, abs_tol=1e-3)  # output z is rounded
    assert ledger.get(hid)["confidence"] == second["new_confidence"]


def test_reanalysing_a_result_does_not_apply_the_update_twice():
    _hypothesis("mtor")
    res_id = tools.run_experiment(_plan_hypothesis_arm())["res_id"]
    first = tools.analyze_result(res_id)
    again = tools.analyze_result(res_id)
    assert len(ledger.rows_of_kind("hypothesis_update")) == 1
    assert again["update_id"] == first["update_id"]
    assert again["new_confidence"] == first["new_confidence"]
    assert again["reward_counted"] is False


# ---------- (4) method A scores, seeded tie-breaking and mid-rank ----------

def test_hypergeom_sf_matches_brute_force():
    # 10 genes, 4 in the set, draw 3: P(X >= 2) = (C(4,2)C(6,1) + C(4,3)) / C(10,3)
    assert math.isclose(scoring.hypergeom_sf(2, 10, 4, 3), (6 * 6 + 4) / 120)
    assert scoring.hypergeom_sf(0, 10, 4, 3) == 1.0


def test_method_a_score_is_continuous_not_overlap_fraction():
    # Old score: both drugs have overlap fraction 1.0 and tie. Two hits is stronger evidence.
    pool = [{"drug_id": "d001", "targets": ["g01"]},
            {"drug_id": "d002", "targets": ["g01", "g02"]},
            {"drug_id": "d003", "targets": ["g30", "g31"]}]
    ranked = scoring.pathway_enrichment(pool, ["GS_IL6"], 2013, seed=0)
    scores = {r["drug_id"]: r["score"] for r in ranked}
    assert scores["d002"] > scores["d001"] > scores["d003"] == 0.0


def test_ties_are_broken_by_seed_not_drug_id():
    pool = [{"drug_id": f"d{i:03d}", "targets": ["g30"]} for i in range(1, 21)]
    orders = {s: [r["drug_id"] for r in scoring.pathway_enrichment(pool, ["GS_IL6"], 2013, seed=s)]
              for s in range(5)}
    assert orders[0] == [r["drug_id"] for r in
                         scoring.pathway_enrichment(pool, ["GS_IL6"], 2013, seed=0)]
    assert len({tuple(o) for o in orders.values()}) > 1  # the seed changes the order
    assert all(o != sorted(o) for o in orders.values())  # never plain drug-id order
    reversed_pool = list(reversed(pool))  # and pool order does not matter
    assert orders[3] == [r["drug_id"] for r in
                         scoring.pathway_enrichment(reversed_pool, ["GS_IL6"], 2013, seed=3)]


def test_target_rank_is_mid_rank_of_its_tie_group(monkeypatch):
    ranked = [{"drug_id": "d009", "score": 2.0, "rank": 1},
              {"drug_id": "d007", "score": 1.0, "rank": 2},
              {"drug_id": "d042", "score": 1.0, "rank": 3},
              {"drug_id": "d001", "score": 1.0, "rank": 4},
              {"drug_id": "d002", "score": 0.0, "rank": 5}]
    assert scoring.mid_rank(ranked, "d042") == 3.0
    assert scoring.mid_rank(ranked, "d009") == 1.0
    assert scoring.mid_rank(ranked, "d999") is None
    monkeypatch.setattr(scoring, "target_drug_id", lambda: "d007")
    scoring.log_target_rank_eval_only("res_001", ranked)
    assert ledger.read_eval_only("res_001")["target_drug_rank"] == 3.0

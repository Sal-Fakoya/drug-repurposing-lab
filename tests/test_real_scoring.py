"""Real-mode scoring: masked pool, snapshot gene sets, eval-only target, tie-aware ranks, method A only.

Uses a synthetic snapshot and mask (no real data), so it runs in CI. Toy mode is covered by the
existing suite and must stay unchanged.
"""
import json

import pytest

import lab
from lab import ledger, masking, scoring, snapshot, toy_data

N = 300                                   # more drugs than the old 200-row truncation
DRUGS = [f"CHEMBL{i}" for i in range(1, N + 1)]
TIED = DRUGS[:5]                          # five drugs whose only target is X (a five-way tie)
TARGET = "CHEMBL3"                        # sits in the middle of that tie group
SET_X = {"X"}


def _snapshot():
    curated = [(d, "X") for d in TIED] + [(d, f"G{i}") for i, d in enumerate(DRUGS[5:60])]
    activity = curated + [(TARGET, "Y")]  # analysis 2 adds a target to the target drug, never a drug
    links = {"curated": sorted(curated), "curated+activity": sorted(activity)}
    sets = {"c2.cp": {"SET_X": SET_X, "SET_Y": {"Y"}, "SET_NOHIT": {"Z"}}}
    return snapshot.Snapshot(2015, "h" * 64, DRUGS, links, sets, {})


@pytest.fixture
def real(tmp_path, monkeypatch):
    snap = _snapshot()
    names = {d: f"name-{d}" for d in DRUGS}
    masking.init(DRUGS, names, TARGET, snap.sha256, tmp_path / "eval", salt="test-salt")
    monkeypatch.setattr(masking, "EVAL_DIR", tmp_path / "eval")
    monkeypatch.setattr(scoring, "MODE", "real")
    monkeypatch.setattr(scoring, "_snapshot", lambda year: snap)
    monkeypatch.delenv("LAB_LINK_DEFINITION", raising=False)
    monkeypatch.delenv("LAB_TARGET_DRUG", raising=False)
    for fn in (scoring._masked_pool, scoring._neg_control):
        fn.cache_clear()
    yield masking.load(tmp_path / "eval")
    for fn in (scoring._masked_pool, scoring._neg_control):
        fn.cache_clear()


def test_pool_is_masked_complete_and_follows_the_link_definition(real, monkeypatch):
    pool = scoring.masked_drug_pool(2015)
    assert len(pool) == N and "CHEMBL" not in json.dumps(pool)
    assert [p["drug_id"] for p in pool] == sorted(p["drug_id"] for p in pool)
    targets = {real.unmask(p["drug_id"]): p["targets"] for p in pool}
    assert targets[TARGET] == ["X"]                                      # Analysis 1 (default)
    monkeypatch.setenv("LAB_LINK_DEFINITION", "curated+activity")
    targets2 = {real.unmask(p["drug_id"]): p["targets"] for p in scoring.masked_drug_pool(2015)}
    assert targets2[TARGET] == ["X", "Y"] and len(targets2) == N          # same drugs, more targets


def test_bad_link_definition_is_refused(real, monkeypatch):
    monkeypatch.setenv("LAB_LINK_DEFINITION", "by-name")
    with pytest.raises(ValueError, match="LAB_LINK_DEFINITION"):
        scoring.masked_drug_pool(2015)


def test_gene_sets_come_from_the_snapshot_by_name_and_typos_fail(real):
    assert scoring._gene_union(["SET_X", "SET_Y"]) == {"X", "Y"}
    with pytest.raises(ValueError, match="unknown gene set 'SET_TYPO'"):
        scoring._gene_union(["SET_X", "SET_TYPO"])


def test_negative_control_is_fixed_eight_genes_shared_by_both_analyses(real, monkeypatch):
    a = scoring._gene_union([toy_data.NEGATIVE_CONTROL])
    assert len(a) == scoring.NEG_CONTROL_SIZE
    universe = {acc for _, acc in _snapshot().links["curated+activity"]}
    assert a <= universe
    monkeypatch.setenv("LAB_LINK_DEFINITION", "curated+activity")
    scoring._neg_control.cache_clear()
    assert scoring._gene_union([toy_data.NEGATIVE_CONTROL]) == a


def test_target_and_names_come_only_from_the_eval_only_files(real, monkeypatch):
    mid = scoring.target_drug_id()
    assert mid == real.mask(TARGET) and mid.startswith("m_")
    assert scoring.unmask(mid) == f"name-{TARGET}"
    with pytest.raises(ValueError, match="unknown masked id"):
        scoring.unmask("m_0000000000")
    monkeypatch.setenv("LAB_TARGET_DRUG", "m_explicit")
    assert scoring.target_drug_id() == "m_explicit"


def test_real_mode_fails_closed_without_the_mask(tmp_path, monkeypatch):
    monkeypatch.setattr(masking, "EVAL_DIR", tmp_path / "none")
    monkeypatch.setattr(scoring, "MODE", "real")
    with pytest.raises(FileNotFoundError, match="lab.masking"):
        scoring.target_drug_id()
    with pytest.raises(FileNotFoundError):
        scoring.unmask("m_whatever")


@pytest.mark.parametrize("run_seed", range(6))
def test_target_mid_rank_is_its_tie_group_whatever_the_seed(real, run_seed):
    """A five-way tie must read 3.0, and the zero-score group must not be cut at 200 rows."""
    pool = scoring.masked_drug_pool(2015)
    ranked = scoring.pathway_enrichment(pool, ["SET_X"], 2015, seed=run_seed)
    assert len(ranked) == N                                              # no truncation
    target = real.mask(TARGET)
    assert scoring.mid_rank(ranked, target) == 3.0                       # ranks 1..5, tied
    assert scoring.target_mid_rank(ranked, target, N) == 3.0
    nohit = real.mask(DRUGS[100])                                        # no overlap: zero-score group
    assert scoring.mid_rank(ranked, nohit) == (5 + 1 + N) / 2            # ranks 6..N, tied


@pytest.mark.parametrize("tie_seed", range(6))
def test_borda_keeps_ties_so_the_published_ranking_does_not_invent_an_order(real, tie_seed):
    pool = scoring.masked_drug_pool(2015)
    results = [(scoring.pathway_enrichment(pool, ["SET_X"], 2015, seed=s), 0.7) for s in (0, 1, 2)]
    final = scoring.borda(results, tie_seed)
    assert len(final) == N
    assert scoring.mid_rank(final, real.mask(TARGET)) == 3.0              # was a random 1..5 before
    scores = {r["drug_id"]: r["score"] for r in final}
    assert len({scores[real.mask(d)] for d in TIED}) == 1                 # the five stay tied


def test_borda_still_orders_distinct_scores_as_before():
    a = [{"drug_id": "a", "score": 3.0, "rank": 1}, {"drug_id": "b", "score": 2.0, "rank": 2},
         {"drug_id": "c", "score": 1.0, "rank": 3}]
    b = [{"drug_id": "b", "score": 5.0, "rank": 1}, {"drug_id": "a", "score": 4.0, "rank": 2},
         {"drug_id": "c", "score": 1.0, "rank": 3}]
    final = scoring.borda([(a, 1.0), (b, 1.0)], 0)
    assert [r["drug_id"] for r in final] == ["a", "b", "c"] or [r["drug_id"] for r in final] == ["b", "a", "c"]
    assert final[2]["drug_id"] == "c"


def test_enrichment_z_uses_the_configured_cutoff_not_a_hard_coded_year(monkeypatch):
    seen = []
    real_pool = scoring.masked_drug_pool
    monkeypatch.setattr(scoring, "CUTOFF_YEAR", 2016)
    monkeypatch.setattr(scoring, "masked_drug_pool", lambda year: seen.append(year) or real_pool(year))
    scoring.enrichment_z([{"drug_id": "d001", "score": 1.0, "rank": 1}], ["GS_IL6"])
    assert seen == [2016]


def test_real_mode_offers_only_method_a_and_toy_still_offers_both(monkeypatch):
    assert lab.available_methods() == ("A", "B")                          # toy default
    hyp = {"id": "hyp_001", "status": "active", "gene_set_ids": ["SET_X"], "testable": True}
    monkeypatch.setattr(ledger, "hypotheses", lambda: [hyp])
    toy_methods = {a["method"] for a in ledger.active_arms()}
    monkeypatch.setattr(lab, "MODE", "real")
    real_arms = ledger.active_arms()
    assert toy_methods == {"A", "B"} and {a["method"] for a in real_arms} == {"A"}
    assert {a["hyp_id"] for a in real_arms} == {"hyp_001", ledger.CONTROL_HYP_ID}   # control arm kept


def test_method_b_and_the_cooccurrence_baseline_refuse_real_mode_clearly(monkeypatch):
    monkeypatch.setattr(scoring, "MODE", "real")
    with pytest.raises(NotImplementedError, match="method A only"):
        scoring.literature_graph([], ["SET_X"], 2015)
    with pytest.raises(NotImplementedError, match="method A only"):
        scoring.literature_cooccurrence([], 2015)


def test_toy_mode_is_unchanged():
    assert scoring.target_drug_id() == toy_data.PLANTED
    assert scoring.unmask("d042") == "drug_d042"
    assert len(scoring.masked_drug_pool(2015)) == len(toy_data.build()[0])

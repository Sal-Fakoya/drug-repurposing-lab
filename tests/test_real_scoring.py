"""Real-mode scoring: masked snapshot pool, snapshot gene sets, eval-only target and names."""
import functools

import pytest
from test_snapshot import _build

from lab import masking, scoring, snapshot, tools, toy_data

NAMES = {"CHEMBL1": "sirolimus"}


@pytest.fixture
def real(tmp_path, monkeypatch):
    """Fixture snapshot (CHEMBL1: curated FKBP1A, activity adds MTOR; c2.cp SET_A) plus a mask."""
    _build(tmp_path, "snaps")
    snap = snapshot.load(2015, tmp_path / "snaps")
    eval_dir = tmp_path / "eval"
    masking.init(snap.drugs, NAMES, "CHEMBL1", snap.sha256, eval_dir, salt="test-salt")
    monkeypatch.setattr(snapshot, "load", functools.partial(snapshot.load, root=tmp_path / "snaps"))
    monkeypatch.setattr(masking, "load", functools.partial(masking.load, eval_dir))
    monkeypatch.setattr(scoring, "MODE", "real")
    monkeypatch.delenv("LAB_TARGET_DRUG", raising=False)
    monkeypatch.delenv("LAB_LINK_DEFINITION", raising=False)
    scoring._real.cache_clear()
    yield masking.masked_id("test-salt", "CHEMBL1")
    scoring._real.cache_clear()


def test_pool_is_masked_and_follows_the_link_definition(real, monkeypatch):
    assert scoring.masked_drug_pool(2015) == [{"drug_id": real, "targets": ["P62942"]}]
    monkeypatch.setenv("LAB_LINK_DEFINITION", "curated+activity")
    assert scoring.masked_drug_pool(2015) == [{"drug_id": real, "targets": ["P42345", "P62942"]}]
    assert "CHEMBL" not in str(scoring.masked_drug_pool(2015))


def test_unknown_link_definition_is_refused(real, monkeypatch):
    monkeypatch.setenv("LAB_LINK_DEFINITION", "activity")
    with pytest.raises(ValueError, match="LAB_LINK_DEFINITION"):
        scoring.masked_drug_pool(2015)


def test_method_a_scores_against_snapshot_gene_sets(real):
    pool = scoring.masked_drug_pool(2015)
    ranked = scoring.pathway_enrichment(pool, ["SET_A"], 2015, seed=0)
    assert [r["drug_id"] for r in ranked] == [real]
    assert scoring._gene_union(["SET_A"], 2015) == {"P42345", "P62942"}


def test_unknown_gene_set_is_refused_not_scored_as_empty(real):
    with pytest.raises(ValueError, match="NOT_A_SET"):
        scoring._gene_union(["SET_A", "NOT_A_SET"], 2015)


def test_toy_negative_control_does_not_leak_into_real_mode(real):
    with pytest.raises(NotImplementedError, match="negative control"):
        scoring._gene_union([toy_data.NEGATIVE_CONTROL], 2015)


def test_target_and_names_come_from_the_eval_only_files(real, monkeypatch):
    assert scoring.target_drug_id() == real
    assert scoring.unmask(real) == "sirolimus"
    monkeypatch.setenv("LAB_TARGET_DRUG", "m_override")
    assert scoring.target_drug_id() == "m_override"


def test_method_b_and_cooccurrence_still_refuse_in_real_mode(real):
    pool = scoring.masked_drug_pool(2015)
    with pytest.raises(NotImplementedError, match="Europe PMC"):
        scoring.literature_graph(pool, ["SET_A"], 2015)
    with pytest.raises(NotImplementedError, match="Europe PMC"):
        scoring.literature_cooccurrence(pool, 2015)


def test_method_a_experiment_runs_end_to_end_and_logs_the_target_rank(real, monkeypatch):
    from lab import ledger
    monkeypatch.setattr(tools, "MODE", "real")
    hyp = ledger.append("hypothesis", {
        "claim": "mTOR signalling drives the disease", "evidence_ids": ["ev_fixture"],
        "confidence": 0.5, "label": "agent-generated", "status": "active", "gene_set_ids": ["SET_A"],
        "predicted_direction": "enriched", "parent_id": None}, agent="insight")
    exp = ledger.append("experiment_spec", {
        "hyp_id": hyp, "method": "A", "arm_id": f"{hyp}:A", "params": {"gene_set_ids": ["SET_A"]},
        "expected_cost": 1.0, "expected_learning": 1.0, "feasibility": 1.0, "status": "planned",
        "seed": 0, "control": False}, agent="planner")
    out = tools.run_experiment(exp)
    assert out["top_ids"] == [real]
    assert ledger.read_eval_only(out["res_id"])["target_drug_rank"] == 1.0

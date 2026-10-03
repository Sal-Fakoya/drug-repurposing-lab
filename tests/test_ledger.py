import pytest

from lab import ledger

HYP = {"claim": "c", "evidence_ids": ["ev_001"], "confidence": 0.5, "label": "agent-generated",
       "status": "active", "gene_set_ids": ["GS_IL6"]}


def test_append_and_get_roundtrip():
    hid = ledger.append("hypothesis", HYP)
    assert hid == "hyp_001"
    assert ledger.get(hid)["claim"] == "c"


def test_invalid_payload_is_rejected():
    with pytest.raises(ValueError):
        ledger.append("hypothesis", {**HYP, "label": "fact"})


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        ledger.append("nonsense", {})


def test_hypothesis_update_overlays_status():
    hid = ledger.append("hypothesis", HYP)
    ledger.append("hypothesis_update", {"hyp_id": hid, "status": "contested", "confidence": 0.2})
    got = ledger.get(hid)
    assert got["status"] == "contested" and got["confidence"] == 0.2


def test_eval_only_data_is_not_readable_through_get():
    ledger.write_eval_only("res_001", {"target_drug_rank": 4})
    with pytest.raises(KeyError):
        ledger.get("res_001")

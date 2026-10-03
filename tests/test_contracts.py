import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


@pytest.mark.parametrize("path", sorted(CONTRACTS.glob("*.json")), ids=lambda p: p.stem)
def test_schema_is_valid(path):
    Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_result_schema_rejects_target_rank():
    schema = json.loads((CONTRACTS / "result.json").read_text())
    bad = {"exp_id": "exp_001", "ranked_drugs": [], "cost": 1.0, "seed": 0,
           "target_drug_rank": 3}
    assert list(Draft202012Validator(schema).iter_errors(bad))


def test_hypothesis_must_be_labeled_agent_generated():
    schema = json.loads((CONTRACTS / "hypothesis.json").read_text())
    bad = {"claim": "x", "evidence_ids": ["ev_001"], "confidence": 0.5, "label": "fact",
           "status": "active", "gene_set_ids": []}
    assert list(Draft202012Validator(schema).iter_errors(bad))

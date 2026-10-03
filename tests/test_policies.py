from lab import policies


def call(target, **arguments):
    return {"type": "tool_call", "target": target,
            "data": {"name": target, "arguments": arguments}}


def test_cutoff_guard_denies_post_cutoff_and_missing():
    guard = policies.cutoff_guard(2013)
    assert guard(call("search_literature", query="q", cutoff_year=2020))["result"] == "DENY"
    assert guard(call("search_literature", query="q"))["result"] == "DENY"
    assert guard(call("search_literature", query="q", cutoff_year=2013))["result"] == "ALLOW"
    assert guard(call("other_tool", cutoff_year=2020)) is None


def test_mask_guard_denies_names_in_scoring_calls():
    guard = policies.mask_guard(["run_experiment"], ["sirolimus", "castleman"])
    assert guard(call("run_experiment", exp_id="exp_001"))["result"] == "ALLOW"
    assert guard(call("run_experiment", note="score Sirolimus"))["result"] == "DENY"
    assert guard(call("search_literature", query="castleman")) is None


def test_approval_gate_asks_for_publish():
    gate = policies.approval_gate(["publish_final_ranking"])
    assert gate(call("publish_final_ranking", res_id="res_001"))["result"] == "ASK"
    assert gate(call("read_ledger", ids=[])) is None

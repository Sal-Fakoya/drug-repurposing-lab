from pathlib import Path

import yaml

SPEC = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "agents" / "lab_director.yaml").read_text())
SUB = {n: t for n, t in SPEC["tools"].items() if t.get("type") == "agent"}


def allowed(name):
    return set(SUB[name]["tools"])


def test_six_sub_agents():
    assert set(SUB) == {"literature", "insight", "planner", "runner", "analysis", "safety"}


def test_every_sub_agent_has_tools():
    assert all(allowed(n) for n in SUB)


def test_no_sub_agent_tool_uses_inherit():
    # Omnigent 0.16 silently drops `inherit` for type: agent sub-agents, leaving them no tools.
    # Sub-agent tools must alias the full top-level definition (`name: *name`) instead.
    assert not [(n, k) for n, t in SUB.items() for k, v in t["tools"].items() if v == "inherit"]


def test_no_agent_has_shell_or_file_access():
    assert "os_env" not in SPEC
    assert all("os_env" not in t for t in SUB.values())


def test_runner_can_only_run_experiments_and_use_the_ledger():
    assert allowed("runner") == {"read_ledger", "run_experiment", "write_ledger"}


def test_planner_cannot_run_or_analyze():
    assert not allowed("planner") & {"run_experiment", "analyze_result", "publish_final_ranking"}


def test_only_safety_can_publish():
    assert [n for n in SUB if "publish_final_ranking" in allowed(n)] == ["safety"]


def test_only_literature_searches_the_literature():
    assert [n for n in SUB if "search_literature" in allowed(n)] == ["literature"]


def test_required_policies_are_declared():
    assert {"cutoff_guard", "mask_guard", "approval_gate"} <= set(SPEC["policies"])


def test_insight_must_name_gene_sets_and_direction_or_mark_untestable():
    prompt = SUB["insight"]["prompt"]
    assert "gene_set_ids" in prompt and "predicted_direction" in prompt
    assert '"enriched" or "not_enriched"' in prompt and "testable: false" in prompt


def test_director_stops_on_budget_or_no_untested_arm():
    prompt = SPEC["prompt"]
    assert "stable for 2 rounds" not in prompt
    assert "budget is spent or no untested arm remains" in prompt


def test_director_checks_outcome_after_a_policy_pause_or_denial():
    prompt = SPEC["prompt"]
    assert "paused for approval or denied by a policy" in prompt
    assert "do not assume" in prompt and "asking for its outcome" in prompt


def test_planner_reads_a_view_without_results():
    assert "read_ledger" not in allowed("planner")
    assert "read_planner_ledger" in allowed("planner")
    assert SUB["planner"]["tools"]["read_planner_ledger"]["callable"] == (
        "lab.tools.read_planner_ledger")


def test_safety_compiles_and_publishes_a_final_ranking_record():
    assert {"compile_final_ranking", "publish_final_ranking"} <= allowed("safety")
    publish = SPEC["tools"]["publish_final_ranking"]["parameters"]
    assert publish["required"] == ["final_ranking_id"]
    assert "final_ranking_id" in SUB["safety"]["prompt"]


def test_write_ledger_requires_agent_in_the_tool_schema():
    assert "agent" in SPEC["tools"]["write_ledger"]["parameters"]["required"]

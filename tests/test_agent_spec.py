from pathlib import Path

import yaml

SPEC = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "agents" / "lab_director.yaml").read_text())
SUB = {n: t for n, t in SPEC["tools"].items() if t.get("type") == "agent"}


def allowed(name):
    return {k for k, v in SUB[name]["tools"].items() if v == "inherit"}


def test_six_sub_agents():
    assert set(SUB) == {"literature", "insight", "planner", "runner", "analysis", "safety"}


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

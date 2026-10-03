"""Custom Omnigent policies. Verdicts: ALLOW, DENY, ASK. Return None to abstain.

Wired in agents/lab_director.yaml under `policies`. Handler paths are dotted import paths,
so install the repo (`pip install -e .`) in the environment Omnigent runs in.
"""
import json

try:  # types come from Omnigent when it is installed
    from omnigent.policies.schema import PolicyEvent, PolicyResponse
except ImportError:  # keeps tests and CI independent of Omnigent
    PolicyEvent = dict
    PolicyResponse = dict


def cutoff_guard(cutoff_year: int):
    """DENY literature searches without a cutoff or with a cutoff after the lab cutoff."""
    def evaluate(event: PolicyEvent) -> PolicyResponse | None:
        if event["type"] != "tool_call" or event["target"] != "search_literature":
            return None
        year = event["data"]["arguments"].get("cutoff_year")
        if year is None or int(year) > cutoff_year:
            return {"result": "DENY",
                    "reason": f"cutoff_year must be set and at most {cutoff_year}."}
        return {"result": "ALLOW"}
    return evaluate


def mask_guard(scoring_tools: list[str], blocked_terms: list[str]):
    """DENY scoring calls that carry drug or disease names. Scoring uses ids only."""
    blocked = [t.lower() for t in blocked_terms]

    def evaluate(event: PolicyEvent) -> PolicyResponse | None:
        if event["type"] != "tool_call" or event["target"] not in scoring_tools:
            return None
        payload = json.dumps(event["data"]["arguments"]).lower()
        for term in blocked:
            if term in payload:
                return {"result": "DENY",
                        "reason": "Drug and disease names must be masked in scoring calls. "
                                  "Use ids."}
        return {"result": "ALLOW"}
    return evaluate


def approval_gate(gated_tools: list[str]):
    """ASK a human before any consequential tool runs."""
    def evaluate(event: PolicyEvent) -> PolicyResponse | None:
        if event["type"] == "tool_call" and event["target"] in gated_tools:
            return {"result": "ASK",
                    "reason": "Publishing a ranked drug list needs human approval."}
        return None
    return evaluate

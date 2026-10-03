"""Append-only research record. Local JSONL for now; Thierry swaps storage for Delta tables.

Rules enforced here:
- every payload is validated against /contracts before it is stored,
- ids are assigned by the ledger (agents pass ids, not blobs),
- evaluation-only data lives in a separate file that no agent-facing function reads.
"""
import json
import os
import threading
import time
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
RUNTIME = Path(os.environ.get("LAB_RUNTIME_DIR", ROOT / "ledger" / "runtime"))

PREFIX = {
    "evidence_record": "ev",
    "hypothesis": "hyp",
    "hypothesis_update": "upd",
    "experiment_spec": "exp",
    "result": "res",
    "verdict": "ver",
    "safety_review": "saf",
    "approval": "apr",
}
METHOD_COST = {"A": 1.0, "B": 2.0}
MAX_RUNS_PER_ARM = 1  # scoring is deterministic, so a re-run teaches nothing
EVAL_ONLY_KEYS = {"target_drug_rank"}

_lock = threading.RLock()
_validators: dict = {}


def _validator(kind: str) -> Draft202012Validator:
    if kind not in _validators:
        schema = json.loads((CONTRACTS / f"{kind}.json").read_text())
        _validators[kind] = Draft202012Validator(schema)
    return _validators[kind]


def _file(name: str) -> Path:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    return RUNTIME / name


def reset() -> None:
    """Delete all runtime state. Used by tests and by fresh runs."""
    for name in ("ledger.jsonl", "eval_only.jsonl", "arm_stats.json"):
        path = _file(name)
        if path.exists():
            path.unlink()


def _rows() -> list[dict]:
    path = _file("ledger.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _strip(obj):
    """Defensive: remove evaluation-only keys from anything an agent could read."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in EVAL_ONLY_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def append(kind: str, payload: dict, agent: str | None = None, parent_id: str | None = None) -> str:
    """Validate and store a payload. Returns its id. Raises ValueError on a schema violation."""
    if kind not in PREFIX:
        raise ValueError(f"Unknown ledger kind: {kind}. Allowed: {sorted(PREFIX)}")
    errors = sorted(_validator(kind).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors)
        raise ValueError(f"Schema violation for {kind}: {detail}")
    with _lock:
        rows = _rows()
        if kind == "evidence_record" and payload.get("pmid"):
            for row in rows:
                if row["kind"] == kind and row["payload"].get("pmid") == payload["pmid"]:
                    return row["id"]
        n = sum(1 for row in rows if row["kind"] == kind) + 1
        row_id = f"{PREFIX[kind]}_{n:03d}"
        row = {
            "id": row_id,
            "kind": kind,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": agent,
            "parent_id": parent_id,
            "payload": payload,
        }
        with _file("ledger.jsonl").open("a") as handle:
            handle.write(json.dumps(row) + "\n")
    return row_id


def _find(row_id: str) -> dict:
    for row in _rows():
        if row["id"] == row_id:
            return row
    raise KeyError(f"Unknown ledger id: {row_id}")


def get(row_id: str) -> dict:
    """Return a payload with its id, with the latest hypothesis state applied."""
    row = _find(row_id)
    data = {"id": row["id"], "kind": row["kind"], **row["payload"]}
    if row["kind"] == "hypothesis":
        for upd in _rows():
            if upd["kind"] == "hypothesis_update" and upd["payload"]["hyp_id"] == row_id:
                data["status"] = upd["payload"]["status"]
                if "confidence" in upd["payload"]:
                    data["confidence"] = upd["payload"]["confidence"]
    return _strip(data)


def rows_of_kind(kind: str) -> list[dict]:
    return [row for row in _rows() if row["kind"] == kind]


def hypotheses() -> list[dict]:
    return [get(row["id"]) for row in rows_of_kind("hypothesis")]


def spent() -> float:
    return sum(row["payload"]["cost"] for row in rows_of_kind("result"))


def _stats() -> dict:
    path = _file("arm_stats.json")
    if not path.exists():
        return {"arms": {}, "analyzed": []}
    return json.loads(path.read_text())


def active_arms() -> list[dict]:
    """Every active hypothesis paired with each method. Reward history comes from arm stats."""
    stats = _stats()["arms"]
    arms = []
    for hyp in hypotheses():
        if hyp["status"] != "active":
            continue
        for method, cost in METHOD_COST.items():
            arm_id = f"{hyp['id']}:{method}"
            s = stats.get(arm_id, {"n": 0, "mean_reward": 1.0})  # optimistic prior
            if s["n"] >= MAX_RUNS_PER_ARM:
                continue
            arms.append({
                "arm_id": arm_id, "hyp_id": hyp["id"], "method": method, "cost": cost,
                "n": s["n"], "mean_reward": s["mean_reward"], "feasibility": 1.0,
                "params": {"gene_set_ids": hyp["gene_set_ids"]},
            })
    return arms


def update_arm_stats(arm_id: str, res_id: str, reward: float) -> bool:
    """Incremental mean update. Idempotent per result id. Returns False if already counted."""
    with _lock:
        stats = _stats()
        if res_id in stats["analyzed"]:
            return False
        s = stats["arms"].get(arm_id, {"n": 0, "mean_reward": 0.0})
        n = s["n"] + 1
        mean = reward if s["n"] == 0 else s["mean_reward"] + (reward - s["mean_reward"]) / n
        stats["arms"][arm_id] = {"n": n, "mean_reward": mean}
        stats["analyzed"].append(res_id)
        _file("arm_stats.json").write_text(json.dumps(stats))
    return True


def write_eval_only(res_id: str, data: dict) -> None:
    """Evaluation-only data (for example the target drug rank). Never exposed to agents."""
    with _lock, _file("eval_only.jsonl").open("a") as handle:
        handle.write(json.dumps({"res_id": res_id, **data}) + "\n")


def read_eval_only(res_id: str) -> dict | None:
    """For the evaluation harness only. Do not import this from agent-facing tools."""
    path = _file("eval_only.jsonl")
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row["res_id"] == res_id:
            return row
    return None

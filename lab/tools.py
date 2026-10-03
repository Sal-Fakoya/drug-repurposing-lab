"""Function tools exposed to the Omnigent agents. The agents never compute; these tools do.

Handoffs go by id. Every tool returns small JSON-serializable dicts.
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request

import numpy as np

from lab import CUTOFF_YEAR, MODE, ledger, scoring, toy_data

BUDGET_TOTAL = float(os.environ.get("LAB_BUDGET", "20"))
PREDICTED_Z = 2.0  # enrichment a hypothesis predicts for itself. Tune in H8 to H11.
_rng = np.random.default_rng(int(os.environ.get("LAB_SEED", "0")))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------- literature ----------

def search_literature(query: str, cutoff_year: int) -> dict:
    """Search Europe PMC with a hard publication date filter. Returns evidence_ids."""
    if cutoff_year is None or int(cutoff_year) > CUTOFF_YEAR:
        raise ValueError(f"cutoff_year must be set and at most {CUTOFF_YEAR}")
    if MODE == "toy":
        samples = [
            ("T001", "SYNTHETIC: Cytokine signalling in a rare lymphoproliferative disorder",
             "Elevated IL-6 reported in a small case series.", ["IL-6"]),
            ("T002", "SYNTHETIC: Non-response to IL-6 pathway blockade in some patients",
             "A subset of patients showed no improvement.", ["IL-6", "non-response"]),
            ("T003", "SYNTHETIC: Upstream kinase signalling activation in lymph node samples",
             "Phospho-protein staining suggested pathway activation.", ["mTOR"]),
        ]
        ids = []
        for pmid, title, snippet, entities in samples:
            ids.append(ledger.append("evidence_record", {
                "source": "toy", "pmid": pmid, "pub_date": "2012-01-01", "title": title,
                "snippet": snippet, "entities": entities, "retrieved_at": _now()}))
        return {"evidence_ids": ids}
    # Real mode. Not exercised in tests (no network in CI). Verify in H1 to H3.
    last_day = f"{int(cutoff_year) - 1}-12-31"  # cutoff_year is exclusive
    q = f"({query}) AND (FIRST_PDATE:[1900-01-01 TO {last_day}])"
    params = urllib.parse.urlencode(
        {"query": q, "format": "json", "resultType": "core", "pageSize": 25})
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read())
    ids = []
    for rec in data.get("resultList", {}).get("result", []):
        pub = rec.get("firstPublicationDate", "")
        if not pub or int(pub[:4]) >= int(cutoff_year):  # belt and braces on the filter
            continue
        ids.append(ledger.append("evidence_record", {
            "source": "europepmc", "pmid": rec.get("pmid"), "pub_date": pub,
            "title": rec.get("title", ""), "snippet": (rec.get("abstractText") or "")[:600],
            "entities": [], "retrieved_at": _now()}))
    return {"evidence_ids": ids}


def read_evidence(evidence_id: str) -> dict:
    return ledger.get(evidence_id)


def find_gene_set(term: str, cutoff_year: int) -> dict:
    """Resolve a pathway or process term to gene_set_ids. Real mode: query dated pathway data."""
    if MODE != "toy":
        raise NotImplementedError("Wire to dated pathway snapshots (Thierry).")
    gs = toy_data.TERM_TO_GENE_SET.get(term.lower().strip(), "GS_NULL")
    return {"gene_set_ids": [gs]}


# ---------- ledger ----------

def write_ledger(kind: str, payload: dict) -> dict:
    """Validate against /contracts/<kind>.json, append, return {'id': ...}."""
    return {"id": ledger.append(kind, payload)}


def read_ledger(ids: list[str]) -> list[dict]:
    return [ledger.get(i) for i in ids]


# ---------- planner ----------

def planner_select_arms(k: int) -> dict:
    """Gaussian Thompson sampling over active arms (hypothesis x method) within the budget."""
    left = BUDGET_TOTAL - ledger.spent()
    drawn = []
    for arm in ledger.active_arms():
        draw = float(_rng.normal(arm["mean_reward"], 1.0 / math.sqrt(arm["n"] + 1)))
        drawn.append((draw, arm))
    drawn.sort(key=lambda t: t[0], reverse=True)
    chosen, spend = [], 0.0
    for _, arm in drawn:
        if len(chosen) == k:
            break
        if spend + arm["cost"] <= left:
            chosen.append(arm)
            spend += arm["cost"]
    if not chosen:
        return {"exp_ids": [], "budget_left": left, "message": "budget exhausted or no active arms"}
    exp_ids = [ledger.append("experiment_spec", {
        "hyp_id": a["hyp_id"], "method": a["method"], "arm_id": a["arm_id"],
        "params": a["params"], "expected_cost": a["cost"],
        "expected_learning": round(a["mean_reward"], 4), "feasibility": a["feasibility"]},
        agent="planner") for a in chosen]
    return {"exp_ids": exp_ids, "arm_ids": [a["arm_id"] for a in chosen],
            "budget_left": round(left - spend, 4)}


# ---------- runner ----------

def run_experiment(exp_id: str) -> dict:
    """Run one experiment spec with masked scoring. Returns ids and opaque top ids only."""
    spec = ledger.get(exp_id)
    gene_sets = spec["params"]["gene_set_ids"]
    pool = scoring.masked_drug_pool(CUTOFF_YEAR)
    if spec["method"] == "A":
        ranked = scoring.pathway_enrichment(pool, gene_sets, CUTOFF_YEAR)
    else:
        ranked = scoring.literature_graph(pool, gene_sets, CUTOFF_YEAR)
    res_id = ledger.append("result", {
        "exp_id": exp_id, "ranked_drugs": ranked, "cost": spec["expected_cost"],
        "seed": scoring.seed(), "artifact_path": None}, agent="runner")
    scoring.log_target_rank_eval_only(res_id, ranked)  # evaluation only, hidden from agents
    return {"res_id": res_id, "n_ranked": len(ranked), "top_ids": [r["drug_id"] for r in ranked[:5]]}


# ---------- analysis ----------

def analyze_result(res_id: str) -> dict:
    """Label-free analysis. Never touches the target drug. Updates the arm reward history."""
    res = ledger.get(res_id)
    spec = ledger.get(res["exp_id"])
    hyp = ledger.get(spec["hyp_id"])
    z = scoring.enrichment_z(res["ranked_drugs"], hyp["gene_set_ids"])
    new_conf = scoring.update_confidence(hyp["confidence"], z, PREDICTED_Z)
    reward = abs(new_conf - hyp["confidence"]) / max(res["cost"], 1e-6)  # belief shift per cost
    contested = z < 0.5 * PREDICTED_Z
    counted = ledger.update_arm_stats(spec["arm_id"], res_id, reward)
    return {"res_id": res_id, "hyp_id": hyp["id"], "z": round(z, 3), "predicted_z": PREDICTED_Z,
            "new_confidence": new_conf, "reward": round(reward, 4), "contested": contested,
            "reward_counted": counted}


# ---------- publication (gated by the approval_gate policy) ----------

def publish_final_ranking(res_id: str) -> dict:
    """Only reachable after a human approves the ASK raised by the approval_gate policy."""
    res = ledger.get(res_id)
    apr_id = ledger.append("approval", {"res_id": res_id, "decision": "approved"}, agent="safety")
    snapshot = {
        "banner": "Agent-generated hypotheses. Not medical advice. "
                  "Needs laboratory and clinical validation.",
        "res_id": res_id, "approval_id": apr_id,
        "ranking": [{"rank": r["rank"], "drug": scoring.unmask(r["drug_id"]), "score": r["score"]}
                    for r in res["ranked_drugs"][:20]],
    }
    out_dir = ledger.ROOT / "ledger" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{res_id}.json").write_text(json.dumps(snapshot, indent=2))
    return {"published": f"ledger/exports/{res_id}.json", "approval_id": apr_id}

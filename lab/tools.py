"""Function tools exposed to the Omnigent agents. The agents never compute; these tools do.

Handoffs go by id. Every tool returns small JSON-serializable dicts.
"""
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

from lab import CUTOFF_YEAR, MODE, ledger, scoring, toy_data

BUDGET_TOTAL = float(os.environ.get("LAB_BUDGET", "20"))
AGENTS = {"literature", "insight", "planner", "runner", "analysis", "safety"}
# Kinds only a deterministic tool may write: results (run_experiment), verdicts (analyze_result),
# final rankings (compile_final_ranking), approvals (publish_final_ranking), spec status rows.
TOOL_ONLY_KINDS = {"result", "verdict", "final_ranking", "approval", "experiment_update"}
PLANNER_VISIBLE_KINDS = {"hypothesis", "experiment_spec", "verdict"}
_rng = np.random.default_rng(int(os.environ.get("LAB_SEED", "0")))

EUROPEPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPEPMC_PAGE_SIZE = 100
EUROPEPMC_MAX_RECORDS = 1000
EUROPEPMC_RETRIES = 4
EUROPEPMC_TIMEOUT = 60
# A record is HHV-8-related if its title or abstract mentions any of these. Plain mentions
# count, including negations such as "HHV-8-negative".
HHV8_PATTERNS = {
    "HHV-8": re.compile(r"\bHHV[- ]?8\b|\bhuman herpes ?virus[- ]?8\b", re.IGNORECASE),
    "KSHV": re.compile(r"\bKSHV\b", re.IGNORECASE),
    "Kaposi": re.compile(r"\bKaposi", re.IGNORECASE),
    "HIV": re.compile(r"\bHIV\b", re.IGNORECASE),
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------- literature ----------

def hhv8_terms(*texts: str) -> list[str]:
    """Which HHV-8 / KSHV / Kaposi / HIV terms the texts mention, in a fixed order."""
    joined = " ".join(t for t in texts if t)
    return [name for name, pattern in HHV8_PATTERNS.items() if pattern.search(joined)]


def _europepmc_page(query: str, cursor: str) -> dict:
    """One page of Europe PMC results. Retries timeouts, network errors and 5xx/429."""
    params = urllib.parse.urlencode({
        "query": query, "format": "json", "resultType": "core",
        "pageSize": EUROPEPMC_PAGE_SIZE, "cursorMark": cursor})
    request = urllib.request.Request(f"{EUROPEPMC_URL}?{params}",
                                     headers={"User-Agent": "drug-repurposing-lab/0.4"})
    for attempt in range(EUROPEPMC_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=EUROPEPMC_TIMEOUT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise RuntimeError(f"Europe PMC rejected the request: HTTP {exc.code}") from exc
            error = exc
        except (OSError, ValueError) as exc:  # URLError, timeouts, truncated JSON
            error = exc
        if attempt < EUROPEPMC_RETRIES - 1:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Europe PMC failed after {EUROPEPMC_RETRIES} attempts: {error}")


def _store_europepmc_record(rec: dict, cutoff_year: int) -> str | None:
    """Keep only title, abstract and first publication date (plus ids). None if out of range.

    Citation counts, MeSH terms and text-mined annotations are computed today and would leak
    post-cutoff knowledge, so they are never stored.
    """
    pub = rec.get("firstPublicationDate") or ""
    if not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", pub) or int(pub[:4]) >= int(cutoff_year):
        return None  # undated, malformed, or on/after the cutoff: belt and braces on the filter
    title = rec.get("title") or ""
    abstract = rec.get("abstractText") or ""
    terms = hhv8_terms(title, abstract)
    return ledger.append("evidence_record", {
        "source": "europepmc", "pmid": rec.get("pmid"), "pub_date": pub, "title": title,
        "abstract": abstract, "snippet": abstract[:600], "entities": [],
        "retrieved_at": _now(), "hhv8_related": bool(terms), "hhv8_terms": terms},
        agent="literature")


def search_literature(query: str, cutoff_year: int,
                      max_records: int = EUROPEPMC_MAX_RECORDS) -> dict:
    """Search Europe PMC with a hard publication date filter. Returns evidence_ids.

    Real mode pages through every hit with cursorMark (up to max_records), keeps only title,
    abstract and first publication date, and tags HHV-8-related records. Evidence ids are
    unique and in retrieval order; a PMID already in the ledger returns its existing id.
    """
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
            terms = hhv8_terms(title, snippet)
            ids.append(ledger.append("evidence_record", {
                "source": "toy", "pmid": pmid, "pub_date": "2012-01-01", "title": title,
                "abstract": snippet, "snippet": snippet, "entities": entities,
                "retrieved_at": _now(), "hhv8_related": bool(terms), "hhv8_terms": terms},
                agent="literature"))
        return {"evidence_ids": ids}
    last_day = f"{int(cutoff_year) - 1}-12-31"  # cutoff_year is exclusive
    q = f"({query}) AND (FIRST_PDATE:[1900-01-01 TO {last_day}])"
    ids: list[str] = []
    cursor, retrieved = "*", 0
    while retrieved < max_records:
        page = _europepmc_page(q, cursor)
        records = page.get("resultList", {}).get("result", [])
        for rec in records[:max_records - retrieved]:
            retrieved += 1
            row_id = _store_europepmc_record(rec, int(cutoff_year))
            if row_id is not None and row_id not in ids:
                ids.append(row_id)
        next_cursor = page.get("nextCursorMark")
        if not records or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    hhv8 = sum(1 for i in ids if ledger.get(i).get("hhv8_related"))
    return {"evidence_ids": ids, "n_retrieved": retrieved, "n_hhv8_related": hhv8}


def read_evidence(evidence_id: str) -> dict:
    return ledger.get(evidence_id)


def find_gene_set(term: str, cutoff_year: int) -> dict:
    """Resolve a pathway or process term to gene_set_ids. Real mode: query dated pathway data."""
    if MODE != "toy":
        raise NotImplementedError("Wire to dated pathway snapshots (Thierry).")
    gs = toy_data.TERM_TO_GENE_SET.get(term.lower().strip(), "GS_NULL")
    return {"gene_set_ids": [gs]}


# ---------- ledger ----------

def write_ledger(kind: str, payload: dict, agent: str) -> dict:
    """Validate against /contracts/<kind>.json, append, return {'id': ...}.

    `agent` is the writing sub-agent's name and is required. Labels ("agent-generated",
    "synthetic") are added automatically from the kind and the lab mode. Guards:
    - results, verdicts, final rankings, approvals and spec status rows come only from their
      tools, so an agent cannot write a verdict that disagrees with the confidence change;
    - a testable hypothesis must name gene_set_ids and a predicted_direction;
    - a hypothesis_update may not raise confidence (only analyze_result does that);
    - an experiment_spec may not repeat a design that is already planned or run.
    """
    if agent not in AGENTS:
        raise ValueError(f"agent must be one of {sorted(AGENTS)}, got {agent!r}")
    if kind in TOOL_ONLY_KINDS:
        raise ValueError(f"{kind} rows are written by their own tool, not write_ledger")
    payload = dict(payload)
    if kind == "hypothesis":
        payload.setdefault("label", "agent-generated")
        if payload.get("testable", True) is not False:
            if not payload.get("gene_set_ids") or "predicted_direction" not in payload:
                raise ValueError("a testable hypothesis needs gene_set_ids and predicted_direction "
                                 "(enriched or not_enriched); otherwise set testable: false")
    elif kind == "hypothesis_update":
        current = ledger.get(payload.get("hyp_id", ""))
        if payload.get("confidence", current["confidence"]) > current["confidence"]:
            raise ValueError("only analyze_result may raise a hypothesis's confidence")
    elif kind == "experiment_spec":
        key = ledger.design_key(payload.get("hyp_id"), payload.get("method"),
                                payload.get("params"))
        taken = ledger.run_designs() | {
            ledger.design_key(s["hyp_id"], s["method"], s["params"])
            for s in (ledger.get(e) for e in ledger.planned_specs())}
        if key in taken:
            raise ValueError("this design (hypothesis, method, params) is already planned or run")
        payload.setdefault("status", "planned")
        payload.setdefault("seed", scoring.seed())
    return {"id": ledger.append(kind, payload, agent=agent)}


def read_ledger(ids: list[str]) -> list[dict]:
    return [ledger.get(i) for i in ids]


def read_planner_ledger(ids: list[str]) -> dict:
    """The planner's view: hypotheses, specs and verdicts by id, plus arm statistics.

    Results (rankings), evidence and every other kind are withheld.
    """
    rows = []
    for i in ids:
        row = ledger.get(i)
        rows.append(row if row["kind"] in PLANNER_VISIBLE_KINDS
                    else {"id": i, "kind": row["kind"], "error": "not visible to the planner"})
    return {"rows": rows, "arm_stats": ledger.arm_stats()}


# ---------- planner ----------

def planner_select_arms(k: int) -> dict:
    """Gaussian Thompson sampling over untested arms (hypothesis x method) within the budget.

    Untried arms (n=0) come first, at most one arm per hypothesis is chosen per round, and an
    arm whose design was already run is never offered. Specs from an earlier round that were
    never run are marked superseded. Planning charges nothing: budget is charged by
    run_experiment. `stop` is true when the budget is spent or no untested arm remains.
    """
    for exp_id in ledger.planned_specs():
        ledger.append("experiment_update", {"exp_id": exp_id, "status": "superseded",
                                            "reason": "replanned before it was run"},
                      agent="planner")
    left = BUDGET_TOTAL - ledger.spent()
    arms = ledger.active_arms()
    drawn = []
    for arm in arms:
        draw = float(_rng.normal(arm["mean_reward"], 1.0 / math.sqrt(arm["n"] + 1)))
        drawn.append((draw, arm))
    drawn.sort(key=lambda t: (t[1]["n"] > 0, -t[0]))
    chosen, spend, used_hyps = [], 0.0, set()
    for _, arm in drawn:
        if len(chosen) == k:
            break
        if arm["hyp_id"] in used_hyps:
            continue
        if spend + arm["cost"] <= left:
            chosen.append(arm)
            spend += arm["cost"]
            used_hyps.add(arm["hyp_id"])
    if not chosen:
        reason = "no untested arm remains" if not arms else "budget spent"
        return {"exp_ids": [], "budget_left": round(left, 4), "untested_arms": len(arms),
                "stop": True, "message": reason}
    exp_ids = [ledger.append("experiment_spec", {
        "hyp_id": a["hyp_id"], "method": a["method"], "arm_id": a["arm_id"],
        "params": a["params"], "expected_cost": a["cost"],
        "expected_learning": round(a["mean_reward"], 4), "feasibility": a["feasibility"],
        "status": "planned", "seed": scoring.seed(), "control": a["control"]},
        agent="planner") for a in chosen]
    return {"exp_ids": exp_ids, "arm_ids": [a["arm_id"] for a in chosen],
            "budget_left": round(left, 4), "planned_cost": round(spend, 4),
            "untested_arms": len(arms), "stop": False}


# ---------- runner ----------

def run_experiment(exp_id: str) -> dict:
    """Run one experiment spec with masked scoring. Returns ids and opaque top ids only.

    Uses and records the spec's seed. Charges the spec's cost now; refuses when that exceeds
    the remaining budget, when the spec was superseded, or when its design was already run.
    Running an already-run spec again returns the existing result without charging.
    """
    with ledger._lock:
        spec = ledger.get(exp_id)
        if spec["kind"] != "experiment_spec":
            raise ValueError(f"{exp_id} is not an experiment_spec")
        existing = next((r for r in ledger.rows_of_kind("result")
                         if r["payload"]["exp_id"] == exp_id), None)
        if existing is not None:
            ranked = existing["payload"]["ranked_drugs"]
            return {"res_id": existing["id"], "already_run": True, "n_ranked": len(ranked),
                    "top_ids": [r["drug_id"] for r in ranked[:5]]}
        if spec["status"] == "superseded":
            raise ValueError(f"{exp_id} was superseded and must not be run")
        key = ledger.design_key(spec["hyp_id"], spec["method"], spec["params"])
        if key in ledger.run_designs():
            raise ValueError(f"{exp_id} repeats a design that was already run")
        left = BUDGET_TOTAL - ledger.spent()
        if spec["expected_cost"] > left + 1e-9:
            raise ValueError(f"budget exhausted: {exp_id} costs {spec['expected_cost']}, "
                             f"{round(left, 4)} left")
        gene_sets = spec["params"]["gene_set_ids"]
        pool = scoring.masked_drug_pool(CUTOFF_YEAR)
        seed = int(spec.get("seed", scoring.seed()))
        if spec["method"] == "A":
            ranked = scoring.pathway_enrichment(pool, gene_sets, CUTOFF_YEAR, seed=seed)
        else:
            include_hhv8 = bool(spec["params"].get("include_hhv8", True))
            ranked = scoring.literature_graph(pool, gene_sets, CUTOFF_YEAR, seed=seed,
                                              include_hhv8=include_hhv8)
        res_id = ledger.append("result", {
            "exp_id": exp_id, "ranked_drugs": ranked, "cost": spec["expected_cost"],
            "seed": seed, "artifact_path": None}, agent="runner", parent_id=exp_id)
    scoring.log_target_rank_eval_only(res_id, ranked)  # evaluation only, hidden from agents
    return {"res_id": res_id, "seed": seed, "n_ranked": len(ranked),
            "top_ids": [r["drug_id"] for r in ranked[:5]]}


# ---------- analysis ----------

def _verdict_row(res_id: str) -> dict | None:
    return next((r for r in ledger.rows_of_kind("verdict") if r["parent_id"] == res_id), None)


def _analysed_twin(res_id: str, key: str) -> str | None:
    """Id of another result with the same design that already has a verdict, if any."""
    for other in ledger.rows_of_kind("result"):
        if other["id"] == res_id or _verdict_row(other["id"]) is None:
            continue
        spec = ledger.get(other["payload"]["exp_id"])
        if ledger.design_key(spec["hyp_id"], spec["method"], spec["params"]) == key:
            return other["id"]
    return None


def analyze_result(res_id: str) -> dict:
    """Label-free analysis. Never touches the target drug. Updates the arm reward history.

    Compares the measured enrichment with the hypothesis's OWN predicted_direction and writes
    the verdict and the hypothesis_update together, from one rule (scoring.assess), so a
    "supported" verdict can never come with a confidence drop. Only the hypothesis named in the
    result's spec is updated, once per result and once per design: re-analysing a res_id, or
    analysing a second result of an already-analysed design, changes nothing. A
    negative-control result updates no hypothesis.
    """
    with ledger._lock:  # read latest confidence and write the update atomically
        res = ledger.get(res_id)
        spec = ledger.get(res["exp_id"])
        z = scoring.enrichment_z(res["ranked_drugs"], spec["params"]["gene_set_ids"])
        if spec.get("control"):
            counted = ledger.update_arm_stats(spec["arm_id"], res_id, 0.0)
            return {"res_id": res_id, "control": True, "z": round(z, 3),
                    "control_passed": z < scoring.Z_ENRICHED, "contested": False,
                    "reward_counted": counted}
        hyp = ledger.get(spec["hyp_id"])
        recorded = _verdict_row(res_id)
        if recorded is not None:
            v = recorded["payload"]
            return {"res_id": res_id, "hyp_id": hyp["id"], "z": round(z, 3),
                    "predicted_direction": v.get("predicted_direction"), "verdict": v["verdict"],
                    "prior_confidence": v.get("prior_confidence"),
                    "new_confidence": v.get("new_confidence"),
                    "contested": v["verdict"] == "contested", "verdict_id": recorded["id"],
                    "update_id": v.get("update_id"), "reward_counted": False}
        twin = _analysed_twin(res_id, ledger.design_key(spec["hyp_id"], spec["method"],
                                                        spec["params"]))
        if twin is not None:
            return {"res_id": res_id, "hyp_id": hyp["id"], "z": round(z, 3),
                    "duplicate_design": True, "contested": False,
                    "message": f"design already analysed in {twin}; no update"}
        predicted = hyp.get("predicted_direction", "enriched")
        prior = hyp["confidence"]
        verdict, new_conf = scoring.assess(z, predicted, prior)
        contested = verdict == "contested"
        upd_id = ledger.append("hypothesis_update", {
            "hyp_id": hyp["id"], "status": "contested" if contested else "active",
            "confidence": new_conf, "reason": f"{res_id}: z={round(z, 3)}, {verdict}"},
            agent="analysis", parent_id=res_id)
        observed = "enriched" if z >= scoring.Z_ENRICHED else "not enriched"
        synthetic = "; synthetic toy data." if ledger.lab.MODE == "toy" else "."
        ver_id = ledger.append("verdict", {
            "res_id": res_id, "hyp_id": hyp["id"], "verdict": verdict,
            "explanation": (f"Predicted {predicted.replace('_', ' ')} for "
                            f"{', '.join(spec['params']['gene_set_ids'])}; method "
                            f"{spec['method']} measured z={round(z, 3)} ({observed}, threshold "
                            f"{scoring.Z_ENRICHED}). Confidence {prior} -> {new_conf}."),
            "evidence_ids": hyp["evidence_ids"],
            "uncertainty": (f"One experiment (method {spec['method']}, seed {res['seed']}), "
                            f"top-10 hypergeometric z, not replicated{synthetic}"),
            "predicted_direction": predicted, "z": round(z, 4),
            "prior_confidence": prior, "new_confidence": new_conf, "update_id": upd_id},
            agent="analysis", parent_id=res_id)
        reward = abs(new_conf - prior) / max(res["cost"], 1e-6)  # belief shift per cost
        counted = ledger.update_arm_stats(spec["arm_id"], res_id, reward)
    return {"res_id": res_id, "hyp_id": hyp["id"], "z": round(z, 3),
            "predicted_direction": predicted, "verdict": verdict, "prior_confidence": prior,
            "new_confidence": new_conf, "reward": round(reward, 4), "contested": contested,
            "verdict_id": ver_id, "update_id": upd_id, "reward_counted": counted}


# ---------- final ranking and publication ----------

FINAL_METHOD = "confidence-weighted Borda count over results with a supported verdict"


def compile_final_ranking() -> dict:
    """Deterministically combine the results of supported hypotheses into a final_ranking.

    Uses every result whose verdict is "supported" and whose hypothesis is still active. Each
    drug scores sum(confidence * (N - rank + 1) / N) over those results; ties break by seed.
    """
    used = []
    for row in ledger.rows_of_kind("verdict"):
        v = row["payload"]
        hyp = ledger.get(v["hyp_id"])
        if v["verdict"] == "supported" and hyp["status"] == "active":
            used.append((v["res_id"], hyp))
    if not used:
        raise ValueError("no supported results to rank yet")
    scores: dict[str, float] = {}
    for res_id, hyp in used:
        ranked = ledger.get(res_id)["ranked_drugs"]
        n = len(ranked)
        for r in ranked:
            scores[r["drug_id"]] = (scores.get(r["drug_id"], 0.0)
                                    + hyp["confidence"] * (n - r["rank"] + 1) / n)
    seed = scoring.seed()
    ranked = scoring._rank(scores, limit=200, run_seed=seed)
    fin_id = ledger.append("final_ranking", {
        "res_ids": [r for r, _ in used], "hyp_ids": sorted({h["id"] for _, h in used}),
        "ranked_drugs": ranked, "method": FINAL_METHOD, "seed": seed}, agent="safety")
    return {"final_ranking_id": fin_id, "n_results": len(used),
            "top_ids": [r["drug_id"] for r in ranked[:10]]}


def publish_final_ranking(final_ranking_id: str) -> dict:
    """Only reachable after a human approves the ASK raised by the approval_gate policy.

    Publishes a final_ranking record, and only after a passing safety_review of that record.
    """
    fin = ledger.get(final_ranking_id)
    if fin["kind"] != "final_ranking":
        raise ValueError(f"{final_ranking_id} is not a final_ranking; compile one first")
    if not any(r["payload"].get("final_ranking_id") == final_ranking_id and r["payload"]["passed"]
               for r in ledger.rows_of_kind("safety_review")):
        raise ValueError(f"no passing safety_review for {final_ranking_id}")
    apr_id = ledger.append("approval", {
        "res_id": final_ranking_id, "final_ranking_id": final_ranking_id,
        "decision": "approved"}, agent="safety", parent_id=final_ranking_id)
    snapshot = {
        "banner": "Agent-generated hypotheses. Not medical advice. "
                  "Needs laboratory and clinical validation.",
        "final_ranking_id": final_ranking_id, "approval_id": apr_id,
        "source_res_ids": fin["res_ids"], "hyp_ids": fin["hyp_ids"], "method": fin["method"],
        "synthetic": ledger.lab.MODE == "toy",
        "ranking": [{"rank": r["rank"], "drug": scoring.unmask(r["drug_id"]), "score": r["score"]}
                    for r in fin["ranked_drugs"][:20]],
    }
    out_dir = ledger.ROOT / "ledger" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{final_ranking_id}.json").write_text(json.dumps(snapshot, indent=2))
    return {"published": f"ledger/exports/{final_ranking_id}.json", "approval_id": apr_id}

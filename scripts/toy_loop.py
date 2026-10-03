"""Deterministic, LLM-free run of the full loop on synthetic data.

Use it to debug tools, ledger, bandit and the reopen rule before involving any agent.
Toy results are plumbing checks, never findings.
"""
import sys

from lab import ledger, tools


def run(rounds: int = 10, k: int = 2, verbose: bool = True) -> dict:
    ev = tools.search_literature("idiopathic multicentric castleman disease", 2013)["evidence_ids"]
    seeds = [("IL-6 drives the disease", "il-6", 0.7), ("mTOR signalling drives it", "mtor", 0.5),
             ("JAK signalling drives it", "jak", 0.4), ("Unmapped mechanism", "unknown", 0.3)]
    for claim, term, conf in seeds:
        gs = tools.find_gene_set(term, 2013)["gene_set_ids"]
        tools.write_ledger("hypothesis", {
            "claim": claim, "evidence_ids": ev, "confidence": conf, "label": "agent-generated",
            "status": "active", "gene_set_ids": gs, "parent_id": None})
    history = []
    for r in range(1, rounds + 1):
        sel = tools.planner_select_arms(k)
        if not sel["exp_ids"]:
            break
        for exp_id in sel["exp_ids"]:
            res = tools.run_experiment(exp_id)
            an = tools.analyze_result(res["res_id"])
            tools.write_ledger("hypothesis_update", {
                "hyp_id": an["hyp_id"], "status": "contested" if an["contested"] else "active",
                "confidence": an["new_confidence"], "reason": f"z={an['z']}"})
            tgt = ledger.read_eval_only(res["res_id"])  # harness only, never shown to agents
            history.append({"round": r, "exp_id": exp_id, "arm": ledger.get(exp_id)["arm_id"],
                            "z": an["z"], "contested": an["contested"],
                            "target_rank": tgt["target_drug_rank"] if tgt else None})
            if verbose:
                print(history[-1])
    return {"spent": ledger.spent(), "history": history}


if __name__ == "__main__":
    ledger.reset()
    out = run()
    print("spent:", out["spent"], "of", tools.BUDGET_TOTAL)
    sys.exit(0)

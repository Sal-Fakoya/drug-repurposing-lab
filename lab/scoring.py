"""Scoring methods A (pathway enrichment) and B (literature graph). Names never enter here.

Everything works on opaque drug ids (d001...) and gene set ids. Real-data loaders are
Thierry's task: replace the _require_toy() branches with reads from the Delta snapshots.
"""
import math
import os

from lab import MODE, ledger, toy_data


def _require_toy() -> None:
    if MODE != "toy":
        raise NotImplementedError("Real loaders are not wired yet. See data/README.md.")


def seed() -> int:
    return int(os.environ.get("LAB_SEED", "0"))


def masked_drug_pool(cutoff_year: int) -> list[dict]:
    """Opaque drug ids with their targets. No names."""
    _require_toy()
    drugs, _ = toy_data.build()
    return [{"drug_id": d, "targets": t} for d, t in sorted(drugs.items())]


def _gene_union(gene_set_ids: list[str]) -> set[str]:
    out: set[str] = set()
    for gs in gene_set_ids:
        out.update(toy_data.GENE_SETS.get(gs, []))
    return out


def _rank(scores: dict[str, float], limit: int) -> list[dict]:
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [{"drug_id": d, "score": round(s, 4), "rank": i + 1} for i, (d, s) in enumerate(ordered)]


def pathway_enrichment(pool: list[dict], gene_set_ids: list[str], cutoff_year: int,
                       limit: int = 200) -> list[dict]:
    """Method A: fraction of a drug's targets that fall in the hypothesis gene set."""
    genes = _gene_union(gene_set_ids)
    scores = {p["drug_id"]: len(genes & set(p["targets"])) / max(len(p["targets"]), 1)
              for p in pool}
    return _rank(scores, limit)


def literature_graph(pool: list[dict], gene_set_ids: list[str], cutoff_year: int,
                     limit: int = 200) -> list[dict]:
    """Method B: co-mention strength between each drug and the hypothesis gene sets."""
    _require_toy()
    _, comentions = toy_data.build()
    scores = {p["drug_id"]: float(sum(comentions.get((p["drug_id"], gs), 0) for gs in gene_set_ids))
              for p in pool}
    return _rank(scores, limit)


def enrichment_z(ranked: list[dict], gene_set_ids: list[str], k: int = 10) -> float:
    """z-score of hypothesis-consistent drugs in the top k versus chance (hypergeometric)."""
    pool = masked_drug_pool(2013)
    genes = _gene_union(gene_set_ids)
    hit = {p["drug_id"] for p in pool if genes & set(p["targets"])}
    n, big_k = len(pool), len(hit)
    observed = sum(1 for r in ranked[:k] if r["drug_id"] in hit)
    expected = k * big_k / n
    var = k * (big_k / n) * (1 - big_k / n) * (n - k) / (n - 1)
    return 0.0 if var <= 0 else (observed - expected) / math.sqrt(var)


def update_confidence(confidence: float, z: float, predicted: float) -> float:
    support = max(0.0, min(z / predicted, 1.5)) / 1.5
    return round(0.5 * confidence + 0.5 * support, 4)


def target_drug_id() -> str | None:
    return os.environ.get("LAB_TARGET_DRUG", toy_data.PLANTED if MODE == "toy" else None)


def log_target_rank_eval_only(res_id: str, ranked: list[dict]) -> None:
    """Write the target drug rank to the evaluation-only table. No agent tool reads it."""
    target = target_drug_id()
    if target is None:
        return
    rank = next((r["rank"] for r in ranked if r["drug_id"] == target), None)
    ledger.write_eval_only(res_id, {"target_drug_rank": rank})


def unmask(drug_id: str) -> str:
    """Id to display name. Only used when publishing an approved ranking."""
    return f"drug_{drug_id}" if MODE == "toy" else drug_id

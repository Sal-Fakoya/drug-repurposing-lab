"""Scoring methods A (pathway enrichment) and B (literature graph). Names never enter here.

Everything works on opaque drug ids (d001...) and gene set ids. Real-data loaders are
Thierry's task: replace the _require_toy() branches with reads from the Delta snapshots.
"""
import hashlib
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


def _tie_key(drug_id: str, run_seed: int) -> str:
    """Seed-dependent, pool-order-independent tie breaker. Drug ids carry no ranking signal."""
    return hashlib.sha256(f"{run_seed}:{drug_id}".encode()).hexdigest()


def _rank(scores: dict[str, float], limit: int, run_seed: int | None = None) -> list[dict]:
    run_seed = seed() if run_seed is None else run_seed
    rounded = {d: round(s, 4) for d, s in scores.items()}  # ties are judged on the stored score
    ordered = sorted(rounded.items(), key=lambda kv: (-kv[1], _tie_key(kv[0], run_seed)))[:limit]
    return [{"drug_id": d, "score": s, "rank": i + 1} for i, (d, s) in enumerate(ordered)]


def hypergeom_sf(x: int, population: int, successes: int, draws: int) -> float:
    """P(X >= x) for X ~ Hypergeometric(population, successes, draws)."""
    total = math.comb(population, draws)
    hi = min(successes, draws)
    return sum(math.comb(successes, i) * math.comb(population - successes, draws - i)
               for i in range(max(x, 0), hi + 1)) / total


def pathway_enrichment(pool: list[dict], gene_set_ids: list[str], cutoff_year: int,
                       limit: int = 200, seed: int | None = None) -> list[dict]:
    """Method A: -log10 hypergeometric p-value of a drug's target overlap with the gene set.

    The gene universe is every gene targeted by the pool plus the gene set itself. A drug with
    no overlap scores 0. Remaining ties are broken by the run seed, not by drug id.
    """
    genes = _gene_union(gene_set_ids)
    universe = genes.union(*(p["targets"] for p in pool))
    scores = {}
    for p in pool:
        targets = set(p["targets"])
        pval = hypergeom_sf(len(genes & targets), len(universe), len(genes), len(targets))
        scores[p["drug_id"]] = -math.log10(pval) if pval > 0 else 300.0
    return _rank(scores, limit, seed)


def literature_graph(pool: list[dict], gene_set_ids: list[str], cutoff_year: int,
                     limit: int = 200, seed: int | None = None) -> list[dict]:
    """Method B: co-mention strength between each drug and the hypothesis gene sets."""
    _require_toy()
    _, comentions = toy_data.build()
    scores = {p["drug_id"]: float(sum(comentions.get((p["drug_id"], gs), 0) for gs in gene_set_ids))
              for p in pool}
    return _rank(scores, limit, seed)


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


def mid_rank(ranked: list[dict], drug_id: str) -> float | None:
    """Mid-rank of the drug's tie group: the mean of the first and last rank sharing its score.

    Ties are not resolved in the target's favour or against it by the seeded tie breaker.
    Returns None if the drug is not in the list.
    """
    score = next((r["score"] for r in ranked if r["drug_id"] == drug_id), None)
    if score is None:
        return None
    tied = [r["rank"] for r in ranked if r["score"] == score]
    return (min(tied) + max(tied)) / 2


def log_target_rank_eval_only(res_id: str, ranked: list[dict]) -> None:
    """Write the target drug mid-rank to the evaluation-only table. No agent tool reads it."""
    target = target_drug_id()
    if target is None:
        return
    ledger.write_eval_only(res_id, {"target_drug_rank": mid_rank(ranked, target)})


def unmask(drug_id: str) -> str:
    """Id to display name. Only used when publishing an approved ranking."""
    return f"drug_{drug_id}" if MODE == "toy" else drug_id

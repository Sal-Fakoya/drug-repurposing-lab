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
                     limit: int = 200, seed: int | None = None,
                     include_hhv8: bool = True) -> list[dict]:
    """Method B: co-mention strength between each drug and the hypothesis gene sets.

    include_hhv8=False drops co-mentions from records with hhv8_status "positive" only
    (HHV-8, KSHV, Kaposi or HIV present or causal; see lab/hhv8.py). Records that only negate
    them ("HHV-8-negative", typical of idiopathic MCD) are kept. The real loader must count
    co-mentions only from evidence whose hhv8_status is not "positive" in that case.
    """
    _require_toy()
    _, comentions = toy_data.build()
    hhv8 = {} if include_hhv8 else toy_data.hhv8_positive_comentions()
    scores = {p["drug_id"]: float(sum(comentions.get((p["drug_id"], gs), 0)
                                      - hhv8.get((p["drug_id"], gs), 0) for gs in gene_set_ids))
              for p in pool}
    return _rank(scores, limit, seed)


Z_ENRICHED = 1.0  # z at or above this counts as "enriched". Tune in H8 to H11.


def _set_z(ranked: list[dict], pool: list[dict], gene_set_id: str, k: int) -> float:
    """Hypergeometric z of drugs targeting one gene set in the top k versus chance."""
    genes = _gene_union([gene_set_id])
    hit = {p["drug_id"] for p in pool if genes & set(p["targets"])}
    n, big_k = len(pool), len(hit)
    observed = sum(1 for r in ranked[:k] if r["drug_id"] in hit)
    expected = k * big_k / n
    var = k * (big_k / n) * (1 - big_k / n) * (n - k) / (n - 1)
    return 0.0 if var <= 0 else (observed - expected) / math.sqrt(var)


def literature_cooccurrence(pool: list[dict], cutoff_year: int, seed: int | None = None,
                            limit: int = 200) -> list[dict]:
    """Baseline: rank drugs by how often they co-occur with the disease in pre-cutoff literature.

    Toy mode uses each drug's total co-mention count over the hypothesis gene sets as its
    literature volume. Real mode needs drug-disease co-occurrence counts from the dated Europe
    PMC snapshot (Thierry's loader); until then it raises like the other loaders.
    """
    _require_toy()
    _, comentions = toy_data.build()
    scores = {p["drug_id"]: float(sum(comentions.get((p["drug_id"], gs), 0)
                                      for gs in toy_data._HYPOTHESIS_SETS)) for p in pool}
    return _rank(scores, limit, seed)


def borda(results: list[tuple[list[dict], float]], seed: int | None = None,
          limit: int = 200) -> list[dict]:
    """Confidence-weighted Borda count: sum(weight * (N - rank + 1) / N) over ranked lists."""
    scores: dict[str, float] = {}
    for ranked, weight in results:
        n = len(ranked)
        for r in ranked:
            scores[r["drug_id"]] = scores.get(r["drug_id"], 0.0) + weight * (n - r["rank"] + 1) / n
    return _rank(scores, limit, seed)


def target_mid_rank(ranked: list[dict], drug_id: str, pool_size: int) -> float:
    """mid_rank, but a drug missing from the list ties with every other unranked drug.

    An empty ranking therefore gives (pool_size + 1) / 2: every drug tied.
    """
    rank = mid_rank(ranked, drug_id)
    if rank is not None:
        return rank
    unranked = pool_size - len(ranked)
    return len(ranked) + (unranked + 1) / 2


def enrichment_z(ranked: list[dict], gene_set_ids: list[str], k: int = 10) -> float:
    """Enrichment of the hypothesis gene sets in the top k, combined across sets (Stouffer).

    Each gene set is tested on its own and the per-set z values are combined as sum / sqrt(m).
    Testing the union instead counts a drug as a hit if it targets ANY of the sets, which
    covers most of the pool once two or three sets are combined and drives z to 0 even when
    the ranking (a sum of the single-set scores) is clearly enriched.
    """
    if not gene_set_ids:
        return 0.0
    pool = masked_drug_pool(2015)
    zs = [_set_z(ranked, pool, gs, k) for gs in gene_set_ids]
    return sum(zs) / math.sqrt(len(zs))


def assess(z: float, predicted_direction: str, confidence: float) -> tuple[str, float]:
    """Verdict and new confidence from ONE rule, so they can never disagree.

    The result matches when the observed direction (z >= Z_ENRICHED is "enriched") equals the
    hypothesis's own prediction. A match is "supported" and moves confidence up; a mismatch is
    "contested" and moves it down. The step grows with the distance of z from the threshold.
    """
    if predicted_direction not in ("enriched", "not_enriched"):
        raise ValueError(f"predicted_direction must be enriched or not_enriched, "
                         f"got {predicted_direction!r}")
    observed = "enriched" if z >= Z_ENRICHED else "not_enriched"
    strength = min(1.0, max(0.1, abs(z - Z_ENRICHED) / 2))
    if observed == predicted_direction:
        return "supported", max(confidence, round(confidence + 0.5 * (1 - confidence) * strength, 4))
    return "contested", min(confidence, round(confidence - 0.5 * confidence * strength, 4))


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

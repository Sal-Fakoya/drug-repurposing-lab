"""Synthetic data so the whole loop runs offline. NEVER report toy results as findings.

Planted structure for debugging: drug d042 targets the MTOR gene set but has little literature.
Drugs d001 to d005 are "famous" for IL-6 (heavy co-mention) with diluted target scores.
GS_NULL is a gene set no drug targets, so a hypothesis on it must come out contested.
"""
from functools import lru_cache

import numpy as np

PLANTED = "d042"
DECOYS = ("d001", "d002", "d003", "d004", "d005")
GENE_SETS = {
    "GS_IL6": [f"g{i:02d}" for i in range(1, 9)],
    "GS_MTOR": [f"g{i:02d}" for i in range(9, 17)],
    "GS_JAK": [f"g{i:02d}" for i in range(17, 25)],
    "GS_NULL": [f"g{i:02d}" for i in range(37, 41)],
}
TERM_TO_GENE_SET = {"il-6": "GS_IL6", "mtor": "GS_MTOR", "jak": "GS_JAK"}


@lru_cache(maxsize=1)
def build(seed: int = 42):
    rng = np.random.default_rng(seed)
    genes = [f"g{i:02d}" for i in range(1, 41)]
    usable = [g for g in genes if g not in GENE_SETS["GS_NULL"]]
    drugs = {}
    for i in range(1, 61):
        k = int(rng.integers(2, 6))
        drugs[f"d{i:03d}"] = sorted(rng.choice(usable, size=k, replace=False).tolist())
    drugs[PLANTED] = ["g09", "g10", "g11", "g30"]
    for did in DECOYS:
        drugs[did] = ["g01", "g02", "g20", "g30", "g31"]
    comentions = {(d, gs): int(rng.poisson(1.0)) for d in drugs for gs in GENE_SETS}
    for did in DECOYS:
        comentions[(did, "GS_IL6")] += 12
    comentions[(PLANTED, "GS_MTOR")] += 2
    return drugs, comentions

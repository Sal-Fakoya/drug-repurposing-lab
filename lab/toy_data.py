"""Synthetic data so the whole loop runs offline. NEVER report toy results as findings.

Planted structure for debugging: drug d042 targets the MTOR gene set but has little literature.
Drugs d001 to d005 are "famous" for IL-6 (heavy co-mention) with diluted target scores.
GS_NULL is a gene set no drug targets, so a hypothesis on it must come out contested.
GS_NEG_CONTROL is a fixed set of 8 random genes (numpy default_rng(20150101), drawn once and
written out below) that the planner can run as a negative control for either method.
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
NEGATIVE_CONTROL = "GS_NEG_CONTROL"
_HYPOTHESIS_SETS = tuple(GENE_SETS)  # drawn first in build(), so adding the control changes nothing
GENE_SETS[NEGATIVE_CONTROL] = ["g02", "g07", "g08", "g10", "g17", "g24", "g32", "g33"]
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
    comentions = {(d, gs): int(rng.poisson(1.0)) for d in drugs for gs in _HYPOTHESIS_SETS}
    for did in DECOYS:
        comentions[(did, "GS_IL6")] += 12
    comentions[(PLANTED, "GS_MTOR")] += 2
    for d in drugs:  # drawn after everything else, so earlier draws are unchanged
        comentions[(d, NEGATIVE_CONTROL)] = int(rng.poisson(1.0))
    return drugs, comentions


HHV8_SHARE = 0.3  # toy: expected share of co-mentions that come from HHV-8-related records


@lru_cache(maxsize=1)
def hhv8_comentions(seed: int = 43) -> dict:
    """The part of each co-mention count that comes from HHV-8-related records.

    Drawn separately (binomial share of the existing counts), so build() is unchanged and
    method B with HHV-8 records included gives exactly the same scores as before.
    """
    _, comentions = build()
    rng = np.random.default_rng(seed)
    return {key: int(rng.binomial(n, HHV8_SHARE)) for key, n in sorted(comentions.items())}

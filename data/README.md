# data

Thierry: date-stamped snapshots of Europe PMC evidence, drug pool, drug-target pairs, pathways.
Record the release or retrieval date of every source here. Anything that cannot be pinned to
the 2015 cutoff must also be listed in LIMITATIONS.md.

## Drug pool

The pool is every drug that is:

1. **approved in ChEMBL 19** (`max_phase = 4`, release 2014-07-03), and
2. has **at least one human target**: a curated `drug_mechanism` link to a target whose organism
   is *Homo sapiens*, matched by UniProt accession (never by target name), and
3. is counted once as its **parent molecule**: salts, hydrates and other forms are merged into
   the parent through `molecule_hierarchy`.

That gives **1146 drugs**. The same pool is used for both pre-registered link definitions: the
sensitivity analysis (curated plus activity <= 1000 nM) adds targets to these drugs but never
adds drugs. Drugs whose only mechanism targets are non-human (antibacterials, antivirals,
antifungals, antiparasitics) or that have no mechanism target are outside the pool.

Implemented once in `lab.chembl.pool_parents` (`lab.chembl.POOL_DEFINITION`) and used by
`lab/snapshot.py` (`data/snapshots/<cutoff>/drug_pool.json`, which the lab reads) and
`scripts/build_snapshots.py` (`data/snapshots/v1/drug_pool.parquet`). Check it independently
with query 6 in `scripts/check_chembl.sql`.

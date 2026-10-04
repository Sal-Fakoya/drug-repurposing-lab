"""Export the real data layer as parquet tables: drug_targets, drug_pool and gene_sets.

    python scripts/build_snapshots.py                       # defaults below
    python scripts/build_snapshots.py --chembl-db PATH --msigdb DIR --out DIR

Inputs: ChEMBL 19 (chembl_19.db, found under data/raw/chembl19) and the MSigDB v4.0 GMT files
(under data/raw/msigdb). Output: data/snapshots/v1/{drug_targets,drug_pool,gene_sets}.parquet
and manifest.json (row counts, SHA-256 of each file, source releases, cutoff year).

Built on lab.chembl and lab.msigdb, so the pre-registered rules apply unchanged (see
docs/cutoff-decision.md and lab/snapshot.py):
- links come from both definitions, "curated" (drug_mechanism, primary) and "curated+activity"
  (sensitivity), recorded per row; targets are human proteins matched by UniProt accession and
  merged to the approved parent molecule;
- gene symbols map to accessions only when unambiguous; ambiguous and unknown symbols are kept
  and labelled, never guessed.
The tables hold ChEMBL ids, never drug names. lab/snapshot.py (JSON) remains the copy the lab
reads; this export is for analysis in pandas and other tools.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lab import CUTOFF_YEAR, chembl, msigdb, snapshot  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "snapshots" / "v1"
DEFAULT_GENES = ("MTOR", "FKBP1A", "IL6")
DEFAULT_DRUGS = ("sirolimus", "tocilizumab", "siltuximab")


def find_chembl_db(root: Path = ROOT / "data" / "raw" / "chembl19") -> Path:
    """chembl_19.db anywhere under root (setup_data.py extracts it to chembl_19_sqlite/)."""
    hits = sorted(Path(root).rglob("chembl_19.db"))
    if not hits:
        raise FileNotFoundError(f"chembl_19.db not found under {root}: run python setup_data.py")
    return hits[0]


def _symbols_by_accession(symbols: dict[str, set[str]]) -> dict[str, str]:
    """accession -> "SYMBOL" (or "A;B" when ChEMBL lists several symbols for one protein)."""
    out: dict[str, set[str]] = {}
    for sym, accs in symbols.items():
        for acc in accs:
            out.setdefault(acc, set()).add(sym)
    return {acc: ";".join(sorted(syms)) for acc, syms in out.items()}


def drug_targets_frame(conn: sqlite3.Connection, symbols: dict[str, set[str]],
                       cutoff_year: int) -> pd.DataFrame:
    by_acc = _symbols_by_accession(symbols)
    rows = [{"definition": d, "drug_chembl_id": drug, "uniprot_accession": acc,
             "gene_symbol": by_acc.get(acc)}
            for d in chembl.DEFINITIONS
            for drug, acc in chembl.drug_target_links(conn, d, cutoff_year)]
    frame = pd.DataFrame(rows, columns=["definition", "drug_chembl_id", "uniprot_accession",
                                        "gene_symbol"])
    return frame.sort_values(list(frame.columns)).reset_index(drop=True)


def drug_pool_frame(conn: sqlite3.Connection, targets: pd.DataFrame) -> pd.DataFrame:
    """Approved parents with at least one target under either definition, with per-definition counts."""
    approved = set(chembl.approved_parents(conn))
    counts = (targets.groupby(["drug_chembl_id", "definition"]).size()
              .unstack(fill_value=0).reindex(columns=list(chembl.DEFINITIONS), fill_value=0))
    counts = counts[counts.index.isin(approved)]
    frame = pd.DataFrame({
        "drug_chembl_id": counts.index,
        "n_targets_curated": counts["curated"].astype("int64").to_numpy(),
        "n_targets_curated_activity": counts["curated+activity"].astype("int64").to_numpy(),
    })
    return frame.sort_values("drug_chembl_id").reset_index(drop=True)


def gene_sets_frame(symbols: dict[str, set[str]], msigdb_root: Path,
                    collections=snapshot.COLLECTIONS) -> tuple[pd.DataFrame, dict[str, str]]:
    """Long table: collection, set_name, gene_symbol, uniprot_accession (if unambiguous), mapping."""
    rows, sources = [], {}
    for col in collections:
        path = msigdb.find_gmt(col, msigdb_root)
        sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for name, genes in msigdb.read_gmt(path).items():
            for gene in genes:
                hit = symbols.get(gene.strip().upper(), set())
                rows.append({"collection": col, "set_name": name, "gene_symbol": gene.strip(),
                             "uniprot_accession": next(iter(hit)) if len(hit) == 1 else None,
                             "mapping": "mapped" if len(hit) == 1 else
                             "ambiguous" if hit else "unmapped"})
    frame = pd.DataFrame(rows, columns=["collection", "set_name", "gene_symbol",
                                        "uniprot_accession", "mapping"])
    frame = frame.drop_duplicates().sort_values(["collection", "set_name", "gene_symbol"])
    return frame.reset_index(drop=True), sources


def _write(frame: pd.DataFrame, path: Path) -> dict:
    frame.to_parquet(path, index=False, engine="pyarrow")
    return {"file": path.name, "rows": len(frame),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build(conn: sqlite3.Connection, msigdb_root: Path, out: Path = DEFAULT_OUT,
          cutoff_year: int = CUTOFF_YEAR, collections=snapshot.COLLECTIONS) -> dict:
    """Write the three parquet tables and manifest.json into out. Returns the manifest."""
    if cutoff_year < snapshot.MIN_CUTOFF_YEAR:
        raise ValueError(f"cutoff {cutoff_year} is before ChEMBL 19 (July 2014): the pins would leak")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    symbols = chembl.symbol_map(conn)
    targets = drug_targets_frame(conn, symbols, cutoff_year)
    pool = drug_pool_frame(conn, targets)
    sets, sources = gene_sets_frame(symbols, msigdb_root, collections)
    tables = {"drug_targets": _write(targets, out / "drug_targets.parquet"),
              "drug_pool": _write(pool, out / "drug_pool.parquet"),
              "gene_sets": _write(sets, out / "gene_sets.parquet")}
    release, created = conn.execute("SELECT name, creation_date FROM version").fetchone()
    manifest = {
        "snapshot": out.name,
        "cutoff_year": cutoff_year,
        "sources": {"chembl": {"release": release, "creation_date": created},
                    "msigdb": {"release": "4.0 (May 2013)", "collections": list(collections),
                               "gmt_sha256": sources}},
        "rules": snapshot.RULES,
        "pool_size": {"curated": int((pool["n_targets_curated"] > 0).sum()),
                      "curated+activity": int((pool["n_targets_curated_activity"] > 0).sum())},
        "tables": tables,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def report(conn: sqlite3.Connection, out: Path, drugs=DEFAULT_DRUGS, genes=DEFAULT_GENES) -> str:
    """Pool size, the named drugs' targets, and the gene sets containing the named genes."""
    targets = pd.read_parquet(out / "drug_targets.parquet")
    sets = pd.read_parquet(out / "gene_sets.parquet")
    manifest = json.loads((out / "manifest.json").read_text())
    lines = [f"Pool size (approved parents with >= 1 human target): "
             f"{manifest['pool_size']['curated']} curated, "
             f"{manifest['pool_size']['curated+activity']} curated+activity", ""]
    for name in drugs:  # names are looked up here only; the tables hold ChEMBL ids
        row = conn.execute("SELECT chembl_id FROM molecule_dictionary WHERE lower(pref_name) = ?",
                           (name.lower(),)).fetchone()
        if row is None:
            lines.append(f"{name}: not in ChEMBL")
            continue
        lines.append(f"{name} ({row[0]}):")
        for definition in chembl.DEFINITIONS:
            hits = targets[(targets["drug_chembl_id"] == row[0])
                           & (targets["definition"] == definition)]
            listed = ", ".join(f"{s or '?'} ({a})" for a, s in
                               zip(hits["uniprot_accession"], hits["gene_symbol"])) or "none"
            lines.append(f"  {definition:17s} {listed}")
    lines.append("")
    for col in sets["collection"].unique():
        in_col = sets[sets["collection"] == col]
        for gene in genes:
            names = sorted(in_col.loc[in_col["gene_symbol"].str.upper() == gene, "set_name"])
            lines.append(f"{col} sets containing {gene} ({len(names)}): " + ", ".join(names))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chembl-db", type=Path, default=None,
                        help="chembl_19.db (default: found under data/raw/chembl19)")
    parser.add_argument("--msigdb", type=Path, default=msigdb.MSIGDB_DIR,
                        help="folder holding the MSigDB v4.0 GMT files")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--collections", nargs="+", default=list(snapshot.COLLECTIONS))
    parser.add_argument("--drugs", nargs="+", default=list(DEFAULT_DRUGS))
    parser.add_argument("--genes", nargs="+", default=list(DEFAULT_GENES))
    args = parser.parse_args(argv)
    conn = chembl.connect(args.chembl_db or find_chembl_db())
    manifest = build(conn, args.msigdb, args.out, collections=args.collections)
    print(report(conn, args.out, args.drugs, args.genes))
    rows = ", ".join(f"{name}: {entry['rows']} rows" for name, entry in manifest["tables"].items())
    print(f"\nwrote {args.out} ({rows})")
    return manifest


if __name__ == "__main__":
    main()

"""Deterministic, hashed snapshot of the real data layer, read by the scoring code.

Build:  python -m lab.snapshot [cutoff_year]      (needs data/raw/ from setup_data.py + MSigDB v4.0)
Layout: data/snapshots/<cutoff_year>/
          drug_pool.json            the drug pool (chembl.POOL_DEFINITION), ChEMBL ids only (no names)
          drug_target_links.json    {"curated": [[drug, uniprot]...], "curated+activity": [...]}
          gene_sets_<collection>.json         {set_name: [uniprot...]}
          gene_set_report_<collection>.json   per-set mapping loss (mapped / ambiguous / unmapped)
          manifest.json             pins, rules, counts, and the SHA-256 of every file above
Files are sorted JSON with no timestamps, so identical inputs give identical bytes, and load()
re-checks every hash. The pool holds real ChEMBL ids: masking is a separate step and the
masked-to-ChEMBL mapping must live in an eval-only file, never here.
"""
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from lab import CUTOFF_YEAR, chembl, msigdb

SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent / "data" / "snapshots"
COLLECTIONS = ("c2.cp", "c2.all")
# ChEMBL 19 is July 2014, so a cutoff before 2015 would let post-cutoff knowledge in.
MIN_CUTOFF_YEAR = 2015
RULES = {
    "curated": "drug_mechanism rows only (Analysis 1, primary)",
    "curated+activity": ("curated plus human IC50/Ki/Kd <= 1000 nM, relation in '=', '<', '<=', "
                         "in documents dated before the cutoff (Analysis 2, sensitivity)"),
    "targets": "matched by UniProt accession, human only, salts collapsed to the parent",
    "pool": chembl.POOL_DEFINITION + "; the same pool for both link definitions",
    "gene_sets": ("MSigDB v4.0 symbols mapped via ChEMBL 19 synonyms; ambiguous symbols excluded, "
                  "unmapped symbols dropped, both counted in gene_set_report_*.json"),
}


def _dump(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1) + "\n").encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot_hash(files: dict[str, str]) -> str:
    return _sha("".join(f"{n}:{h}\n" for n, h in sorted(files.items())).encode())


def build(cutoff_year: int = CUTOFF_YEAR, root: Path = SNAPSHOT_ROOT, conn=None,
          collections=COLLECTIONS, gmt_root: Path = msigdb.MSIGDB_DIR) -> Path:
    """Write the snapshot for one cutoff year and return its folder."""
    if cutoff_year < MIN_CUTOFF_YEAR:
        raise ValueError(f"cutoff {cutoff_year} is before ChEMBL 19 (July 2014): the pins would leak")
    conn = conn or chembl.connect()
    out = Path(root) / str(cutoff_year)
    out.mkdir(parents=True, exist_ok=True)

    pool = chembl.pool_parents(conn)
    in_pool = set(pool)
    links = {d: sorted(p for p in chembl.drug_target_links(conn, d, cutoff_year) if p[0] in in_pool)
             for d in chembl.DEFINITIONS}
    symbols = chembl.symbol_map(conn)
    blobs = {"drug_pool.json": pool, "drug_target_links.json": {d: [list(p) for p in v]
                                                                for d, v in links.items()}}
    sources = {}
    for col in collections:
        gmt = msigdb.find_gmt(col, gmt_root)
        sets, report = msigdb.load_gene_sets(symbols, col, gmt)
        blobs[f"gene_sets_{col}.json"] = {k: sorted(v) for k, v in sets.items()}
        blobs[f"gene_set_report_{col}.json"] = report
        sources[gmt.name] = _sha(gmt.read_bytes())

    files = {}
    for name, obj in blobs.items():
        data = _dump(obj)
        (out / name).write_bytes(data)
        files[name] = _sha(data)
    version = conn.execute("SELECT name, creation_date FROM version").fetchone()
    manifest = {
        "cutoff_year": cutoff_year,
        "chembl": {"release": version[0], "creation_date": version[1]},
        "msigdb": {"version": "4.0 (May 2013)", "source_files_sha256": sources},
        "rules": RULES,
        "counts": {"drugs": len(pool), **{f"links_{d}": len(v) for d, v in links.items()},
                   **{f"sets_{c}": len(blobs[f"gene_sets_{c}.json"]) for c in collections}},
        "files": files,
        "snapshot_sha256": _snapshot_hash(files),
    }
    (out / "manifest.json").write_bytes(_dump(manifest))
    return out


@dataclass(frozen=True)
class Snapshot:
    cutoff_year: int
    sha256: str
    drugs: list[str]
    links: dict[str, list[tuple[str, str]]]
    gene_sets: dict[str, dict[str, set[str]]]   # collection -> set_name -> accessions
    manifest: dict

    def pool(self, definition: str = "curated") -> list[dict]:
        """Pool in the shape lab.scoring uses: every approved parent, with its target accessions."""
        by_drug: dict[str, list[str]] = {d: [] for d in self.drugs}
        for drug, acc in self.links[definition]:
            by_drug[drug].append(acc)
        return [{"drug_id": d, "targets": sorted(t)} for d, t in sorted(by_drug.items())]


def load(cutoff_year: int = CUTOFF_YEAR, root: Path = SNAPSHOT_ROOT) -> Snapshot:
    """Read a snapshot, refusing it if any file no longer matches the manifest."""
    folder = Path(root) / str(cutoff_year)
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, want in manifest["files"].items():
        if _sha((folder / name).read_bytes()) != want:
            raise ValueError(f"{folder / name} does not match the manifest hash: snapshot is corrupt")
    if _snapshot_hash(manifest["files"]) != manifest["snapshot_sha256"]:
        raise ValueError(f"{folder}: manifest was edited")

    def read(name):
        return json.loads((folder / name).read_text())

    links = {d: [tuple(p) for p in v] for d, v in read("drug_target_links.json").items()}
    gene_sets = {n[len("gene_sets_"):-len(".json")]: {k: set(v) for k, v in read(n).items()}
                 for n in manifest["files"] if n.startswith("gene_sets_")}
    return Snapshot(manifest["cutoff_year"], manifest["snapshot_sha256"], read("drug_pool.json"),
                    links, gene_sets, manifest)


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else CUTOFF_YEAR
    folder = build(year)
    snap = load(year)
    print(f"snapshot {year} written to {folder}\nsha256 {snap.sha256}\ncounts {snap.manifest['counts']}")

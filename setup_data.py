"""Rebuild the data/ folder: ChEMBL 19 plus the Europe PMC pre-cutoff record files.

Usage:  python setup_data.py [--no-chembl] [--no-evidence]
Standard library only. Needs network access and ~15 GB of free disk (2.5 GB tarball + 12 GB db).
Safe to re-run: finished steps are skipped and an interrupted download resumes.

Reproducing this data:
- ChEMBL 19 is a fixed archive (July 2014). After this script runs, every machine has an
  identical chembl_19.db: the tarball is checked against a SHA-256 pinned in this file.
- Europe PMC is a live index. Pre-cutoff counts can drift by a few records between runs on
  different days or machines. The go/no-go rule (zero canary matches, at least three IL-6
  non-response sources) is robust to that noise; see docs/cutoff-decision.md.
"""
import argparse
import hashlib
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHEMBL_DIR = ROOT / "data" / "raw" / "chembl19"
TARBALL = CHEMBL_DIR / "chembl_19_sqlite.tar.gz"
DB = CHEMBL_DIR / "chembl_19_sqlite" / "chembl_19.db"
BASE = "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_19"
URL = f"{BASE}/chembl_19_sqlite.tar.gz"
TARBALL_BYTES = 2471647673  # Content-Length from the EBI FTP, used as a fast sanity check
# EBI publishes no checksum for this release, so this is pinned from the team's first download.
TARBALL_SHA256 = "984bc5c4d50a6424d5f2452bb809a50d1249bbb73b07eb70f3655b6827c5120f"
CUTOFF_SWEEP = (2014, 2015, 2016)  # the cutoff sweep recorded in docs/cutoff-decision.md


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download() -> None:
    CHEMBL_DIR.mkdir(parents=True, exist_ok=True)
    have = TARBALL.stat().st_size if TARBALL.exists() else 0
    if have > TARBALL_BYTES:
        sys.exit(f"{TARBALL} is larger than expected; delete it and re-run.")
    if have < TARBALL_BYTES:
        print(f"Downloading ChEMBL 19 ({have / 1e9:.2f} of {TARBALL_BYTES / 1e9:.2f} GB) ...")
        headers = {"Range": f"bytes={have}-"} if have else {}
        req = urllib.request.Request(URL, headers=headers)
        with urllib.request.urlopen(req) as resp, open(TARBALL, "ab" if have else "wb") as out:
            if have and resp.status not in (200, 206):
                sys.exit(f"Unexpected status {resp.status}; delete the partial file and re-run.")
            if have and resp.status == 200:
                print("  server returned the whole file (no range support); restarting ...")
                out.seek(0)
                out.truncate()
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    if TARBALL.stat().st_size != TARBALL_BYTES:
        sys.exit("Download incomplete (size mismatch). Re-run to resume.")
    print("Verifying SHA-256 (reads the whole file, takes a minute) ...")
    actual = sha256_of(TARBALL)
    if actual != TARBALL_SHA256:
        sys.exit(f"SHA-256 mismatch:\n  expected {TARBALL_SHA256}\n  got      {actual}\n"
                 f"Delete {TARBALL} and re-run.")
    print("Checksum OK.")


def extract() -> None:
    if DB.exists():
        return  # already extracted on an earlier run
    print("Extracting (a few minutes) ...")
    with tarfile.open(TARBALL) as tar:
        if sys.version_info >= (3, 12):
            tar.extractall(CHEMBL_DIR, filter="data")
        else:
            tar.extractall(CHEMBL_DIR)
    if not DB.exists():
        sys.exit(f"Expected {DB} after extraction, not found. "
                 f"Check {CHEMBL_DIR} for a different folder layout.")


def chembl() -> None:
    if DB.exists():
        print(f"ChEMBL 19 already present: {DB}")
        return
    download()
    extract()
    print(f"ChEMBL 19 ready: {DB}")


def evidence() -> None:
    for year in CUTOFF_SWEEP:
        print(f"\nEurope PMC records, cutoff {year} ...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "check_europepmc.py"), str(year)],
                       check=False)  # exits 1 if any record is post-cutoff; output shows it


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-chembl", action="store_true", help="skip the 2.5 GB ChEMBL download")
    ap.add_argument("--no-evidence", action="store_true", help="skip the Europe PMC queries")
    args = ap.parse_args()
    if not args.no_chembl:
        chembl()
    if not args.no_evidence:
        evidence()
    print("\nDone. data/ now matches the layout in HANDOFF.md.")
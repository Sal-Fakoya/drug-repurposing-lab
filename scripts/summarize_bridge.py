"""Summarise the bridge evidence: how could the lab reach mTOR without the disease name?

Usage:  python scripts/summarize_bridge.py [CUTOFF_YEAR]
Reads data/sirolimus_lpd_records_<year>.tsv (and il6_pi3k_records_<year>.tsv if present),
written by scripts/check_europepmc.py. Keyword families are a first look, not a classification:
READ the abstracts it lists.
"""
import csv
import re
import sys
from pathlib import Path

try:
    from lab import CUTOFF_YEAR
except ImportError:
    CUTOFF_YEAR = 2015

DATA = Path(__file__).resolve().parent.parent / "data"
FAMILIES = {
    "ALPS (autoimmune lymphoproliferative)": r"autoimmune lymphoproliferative|\bALPS\b",
    "post-transplant (PTLD or transplant)": r"post-?transplant|\bPTLD\b|transplant",
    "lymphoma or leukaemia": r"lymphoma|leuk(?:a)?emia",
    "EBV": r"Epstein|\bEBV\b",
    "Castleman": r"Castleman",
    "mTOR/PI3K/AKT named": r"mTOR|PI3K|\bAKT\b|PI-3K|mammalian target",
}
MECHANISM = re.compile(FAMILIES["mTOR/PI3K/AKT named"])
TRANSPLANT = re.compile(FAMILIES["post-transplant (PTLD or transplant)"], re.IGNORECASE)


def load(name: str, year: int) -> list[dict]:
    path = DATA / f"{name}_{year}.tsv"
    if not path.exists():
        print(f"== {name}: {path.name} not found (run check_europepmc.py {year})")
        return []
    csv.field_size_limit(10_000_000)
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE))


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else CUTOFF_YEAR
    for name in ("sirolimus_lpd_records", "il6_pi3k_records"):
        rows = load(name, year)
        if not rows:
            continue
        print(f"\n== {name} ({year}): {len(rows)} records")
        for label, pattern in FAMILIES.items():
            rx = re.compile(pattern, re.IGNORECASE if "mTOR" not in label else 0)
            n = sum(1 for r in rows if rx.search(f'{r["title"]} {r["abstract"]}'))
            print(f"   {label:42s} {n:>4d}")
        print("\n   Mechanistic records: name mTOR/PI3K/AKT and are NOT transplant papers (up to 30)")
        shown = 0
        for r in rows:
            text = f'{r["title"]} {r["abstract"]}'
            if MECHANISM.search(text) and not TRANSPLANT.search(text):
                print(f'   {r["date"]}  {r["pmid"]:>9}  {r["title"][:75]}')
                shown += 1
                if shown == 30:
                    break
        if shown == 0:
            print("   none")
    print("\nRead the listed abstracts. A thin bridge means the lab is unlikely to reach sirolimus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

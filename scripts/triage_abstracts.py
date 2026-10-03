"""Flag saved abstracts that mention relapse, refractoriness or non-response.

These are CANDIDATES only. Read every flagged abstract: keywords also match unrelated uses.
Usage:  python scripts/triage_abstracts.py [CUTOFF_YEAR]     (default: the lab cutoff)
Reads data/<set>_records_<year>.tsv written by scripts/check_europepmc.py.
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
SETS = ("il6_nonresponse_records", "tocilizumab_records", "siltuximab_records")
PAT = re.compile(r"(relaps\w*|refractory|did not respond|no response|non-?respon\w*|failed|"
                 r"resistan\w*|partial (?:response|remission)|insufficient|durable)", re.IGNORECASE)


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else CUTOFF_YEAR
    csv.field_size_limit(10_000_000)
    seen: set[str] = set()
    for name in SETS:
        path = DATA / f"{name}_{year}.tsv"
        if not path.exists():
            print(f"== {name}: {path.name} not found (run check_europepmc.py {year} first)")
            continue
        print(f"== {name} ({year})")
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE):
                key = row["pmid"] if row["pmid"] != "-" else row["title"]
                text = f'{row["title"]} {row["abstract"]}'
                hits = sorted({m.group(0).lower() for m in PAT.finditer(text)})
                if hits and key not in seen:
                    seen.add(key)
                    print(f'{row["date"]}  {row["pmid"]:>9}  {hits}  {row["title"][:70]}')
    print(f"\n{len(seen)} unique flagged records. Read them before counting any as evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""Europe PMC pre-cutoff checks for the go/no-go (Thierry, H1 to H3). Standard library only.

Needs network access. Run:  python scripts/check_europepmc.py [CUTOFF_YEAR]   (default 2015)
Cutoff is exclusive: documents must be dated before 1 January of CUTOFF_YEAR.

v2 changes: counts are restricted to TITLE or ABSTRACT (default search also matches full text,
which inflates counts with incidental mentions), and the canary and earliest-mention checks
now page through ALL hits instead of sorting only the first relevance-ranked page.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CUTOFF_YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2015
LAST_DAY = f"{CUTOFF_YEAR - 1}-12-31"
OUT = Path(__file__).resolve().parent.parent / "data" / "canary_records.tsv"

DISEASE_TERMS = ["Castleman disease", "Castleman's disease", "angiofollicular lymph node hyperplasia",
                 "giant lymph node hyperplasia"]
VIRAL_TERMS = ["HHV-8", "HHV8", "HHV 8", "human herpesvirus 8", "human herpes virus 8",
               "KSHV", "Kaposi", "HIV"]


def ta(*terms: str) -> str:
    """Match any term in the title or abstract only (not full text)."""
    return "(" + " OR ".join(f'TITLE:"{t}" OR ABSTRACT:"{t}"' for t in terms) + ")"


DISEASE = ta(*DISEASE_TERMS)
IL6 = ta("interleukin-6", "IL-6")
MTOR = ta("sirolimus", "rapamycin", "mTOR")

TOPICS = {
    "disease (title/abstract)": DISEASE,
    "disease, excluding HHV-8/Kaposi/HIV": f"{DISEASE} AND NOT {ta(*VIRAL_TERMS)}",
    "IL-6": f"{DISEASE} AND {IL6}",
    "tocilizumab": f"{DISEASE} AND {ta('tocilizumab')}",
    "IL-6 AND refractory/no response (loose)": (
        f"{DISEASE} AND {IL6} AND {ta('refractory', 'no response', 'nonresponder', 'non-responder')}"),
    "siltuximab": f"{DISEASE} AND {ta('siltuximab')}",
    "rituximab": f"{DISEASE} AND {ta('rituximab')}",
    "CANARY disease AND sirolimus/rapamycin/mTOR": f"{DISEASE} AND {MTOR}",
    "CANARY, excluding HHV-8/Kaposi/HIV": f"{DISEASE} AND {MTOR} AND NOT {ta(*VIRAL_TERMS)}",
    "sirolimus AND lymphoproliferative": f"{ta('sirolimus', 'rapamycin')} AND {ta('lymphoproliferative')}",
}


def search(query: str, page_size: int = 100, cursor: str = "*") -> dict:
    params = urllib.parse.urlencode({"query": query, "format": "json", "resultType": "core",
                                     "pageSize": page_size, "cursorMark": cursor})
    req = urllib.request.Request(f"{BASE}?{params}",
                                 headers={"User-Agent": "drug-repurposing-lab/0.3"})
    last_error = None
    for attempt in range(5):  # Europe PMC sometimes times out on heavy queries: retry with backoff
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
            time.sleep(0.3)  # be polite
            return data
        except OSError as exc:  # includes TimeoutError and URLError
            last_error = exc
            wait = 2 ** (attempt + 1)
            print(f"   (retry {attempt + 1}/5 after {type(exc).__name__}, waiting {wait}s)",
                  file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Europe PMC request failed after 5 attempts: {last_error}")


def fetch_all(query: str, limit: int = 1000) -> list[dict]:
    """Page through every hit with cursorMark (not just the first relevance-ranked page)."""
    out, cursor = [], "*"
    while len(out) < limit:
        page = search(query, page_size=100, cursor=cursor)
        out.extend(page.get("resultList", {}).get("result", []))
        nxt = page.get("nextCursorMark")
        if not nxt or nxt == cursor or not page.get("resultList", {}).get("result"):
            break
        cursor = nxt
    return out[:limit]


def dated(query: str) -> str:
    return f"({query}) AND (FIRST_PDATE:[1900-01-01 TO {LAST_DAY}])"


def hits(query: str) -> int:
    return int(search(dated(query), page_size=1)["hitCount"])


def rows(records: list[dict]) -> list[tuple]:
    return sorted((r.get("firstPublicationDate") or "9999", r.get("pmid") or "-",
                   (r.get("title") or "").replace("\t", " ")) for r in records)


def dump(name: str, query: str) -> list[tuple]:
    """Fetch every pre-cutoff hit and save date, pmid, title and abstract to data/<name>.tsv."""
    recs = fetch_all(dated(query))
    ordered = sorted(recs, key=lambda r: r.get("firstPublicationDate") or "9999")
    path = OUT.parent / f"{name}_{CUTOFF_YEAR}.tsv"
    lines = ["date\tpmid\ttitle\tabstract"]
    for r in ordered:
        abstract = (r.get("abstractText") or "").replace("\t", " ").replace("\n", " ")[:6000]
        lines.append("\t".join([r.get("firstPublicationDate") or "", r.get("pmid") or "-",
                                 (r.get("title") or "").replace("\t", " "), abstract]))
    OUT.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    print(f"   {len(ordered)} records saved to {path}")
    return rows(ordered)


def main() -> int:
    print(f"Cutoff: publications dated up to {LAST_DAY} (exclusive year {CUTOFF_YEAR})\n")
    print("1. Pre-cutoff hit counts (title/abstract only)")
    for name, q in TOPICS.items():
        print(f"   {name:46s} {hits(q):>7d}")

    print("\n2. Does the date filter work? (sample of the disease query)")
    recs = search(dated(DISEASE), page_size=100)["resultList"]["result"]
    dates = sorted(r["firstPublicationDate"] for r in recs if r.get("firstPublicationDate"))
    late = [d for d in dates if int(d[:4]) >= CUTOFF_YEAR]
    print(f"   sampled {len(recs)} records, dates {dates[0]} to {dates[-1]}, after cutoff: {len(late)}")

    print("\n3. CANARY records BEFORE the cutoff (disease with sirolimus/rapamycin/mTOR). READ THESE.")
    canary = dump("canary_records", f"{DISEASE} AND {MTOR}")
    for d, pmid, title in canary[:25]:
        print(f"   {d}  PMID {pmid}  {title[:100]}")

    print("\n4. Earliest records mentioning the mechanism with the disease, no date filter (all hits)")
    for d, pmid, title in rows(fetch_all(f"{DISEASE} AND {MTOR}"))[:5]:
        print(f"   {d}  PMID {pmid}  {title[:100]}")

    print("\n5. Evidence the IL-6 demo moment depends on (records saved with abstracts, READ THEM)")
    dump("il6_nonresponse_records", TOPICS["IL-6 AND refractory/no response (loose)"])
    dump("tocilizumab_records", TOPICS["tocilizumab"])
    dump("siltuximab_records", TOPICS["siltuximab"])

    print("\nUse only title, abstract and firstPublicationDate downstream. Do NOT use citedByCount,")
    print("text-mined annotations or MeSH terms: they are computed today and leak post-cutoff knowledge.")
    return 0 if not late else 1


if __name__ == "__main__":
    sys.exit(main())
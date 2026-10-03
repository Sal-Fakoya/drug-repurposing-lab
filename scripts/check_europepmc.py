"""Europe PMC pre-cutoff checks for the go/no-go (Thierry, H1 to H3). Standard library only.

Needs network access. Run:  python scripts/check_europepmc.py
Cutoff is exclusive: documents must be dated before 1 January of CUTOFF_YEAR.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CUTOFF_YEAR = 2013
LAST_DAY = f"{CUTOFF_YEAR - 1}-12-31"

DISEASE_TERMS = ["Castleman disease", "Castleman's disease",
                 "angiofollicular lymph node hyperplasia", "giant lymph node hyperplasia"]
DISEASE = "(" + " OR ".join(f'"{t}"' for t in DISEASE_TERMS) + ")"

TOPICS = {
    "disease (all, with abstract)": f"{DISEASE} AND HAS_ABSTRACT:y",
    "IL-6": f'{DISEASE} AND ("interleukin-6" OR "IL-6")',
    "tocilizumab": f"{DISEASE} AND tocilizumab",
    "IL-6 blockade non-response": (f'{DISEASE} AND ("interleukin-6" OR "IL-6") AND '
                                   '(refractory OR "no response" OR nonresponder '
                                   'OR "did not respond")'),
    "rituximab": f"{DISEASE} AND rituximab",
    "CANARY sirolimus/rapamycin/mTOR": f"{DISEASE} AND (sirolimus OR rapamycin OR mTOR)",
    "sirolimus in lymphoproliferative disease": ('(sirolimus OR rapamycin) AND '
                                                 '("lymphoproliferative" OR '
                                                 '"autoimmune lymphoproliferative")'),
}


def search(query: str, page_size: int = 100, cursor: str = "*") -> dict:
    params = urllib.parse.urlencode({"query": query, "format": "json", "resultType": "core",
                                     "pageSize": page_size, "cursorMark": cursor})
    req = urllib.request.Request(f"{BASE}?{params}",
                                 headers={"User-Agent": "drug-repurposing-lab/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    time.sleep(0.3)  # be polite
    return data


def dated(query: str) -> str:
    return f"({query}) AND (FIRST_PDATE:[1900-01-01 TO {LAST_DAY}])"


def hits(query: str) -> int:
    return int(search(dated(query), page_size=1)["hitCount"])


def main() -> int:
    print(f"Cutoff: publications dated up to {LAST_DAY} (exclusive year {CUTOFF_YEAR})\n")
    print("1. Pre-cutoff hit counts")
    for name, q in TOPICS.items():
        print(f"   {name:45s} {hits(q):>7d}")

    print("\n2. Does the date filter work? (sample of the disease query)")
    recs = search(dated(DISEASE), page_size=100)["resultList"]["result"]
    dates = sorted(r["firstPublicationDate"] for r in recs if r.get("firstPublicationDate"))
    late = [d for d in dates if int(d[:4]) >= CUTOFF_YEAR]
    print(f"   sampled {len(recs)} records, dates {dates[0]} to {dates[-1]}, "
          f"after cutoff: {len(late)}")
    post = int(search(f"{DISEASE} AND (FIRST_PDATE:[{CUTOFF_YEAR}-01-01 TO {CUTOFF_YEAR}-12-31])",
                      page_size=1)["hitCount"])
    print(f"   same disease query dated {CUTOFF_YEAR} (must be excluded above): {post}")

    print("\n3. Earliest records mentioning the target mechanism with the disease (no date filter)")
    q = f"{DISEASE} AND (sirolimus OR rapamycin OR mTOR)"
    recs = search(q, page_size=200)["resultList"]["result"]
    rows = sorted((r.get("firstPublicationDate", "9999"), r.get("pmid", "-"),
                   r.get("title", "")[:90]) for r in recs)
    for d, pmid, title in rows[:5]:
        print(f"   {d}  PMID {pmid}  {title}")

    print("\nUse only title, abstract and firstPublicationDate downstream. "
          "Do NOT use citedByCount,")
    print("text-mined annotations or MeSH terms: they are computed today "
          "and leak post-cutoff knowledge.")
    return 0 if not late else 1


if __name__ == "__main__":
    sys.exit(main())

import csv
import re

PAT = re.compile(r"(relaps\w*|refractory|did not respond|no response|non-?respon\w*|failed|"
                 r"resistan\w*|partial (?:response|remission)|insufficient)", re.I)
for name in ("tocilizumab_records", "il6_nonresponse_records"):
    print("==", name)
    with open(f"data/{name}.tsv", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            hits = sorted({m.group(0).lower() for m in PAT.finditer(f'{row["title"]} {row["abstract"]}')})
            if hits:
                print(row["date"], row["pmid"], hits, "|", row["title"][:80])

"""Set the lab cutoff year everywhere it is written down.

Usage:
    python scripts/set_cutoff.py 2015            # rewrite files in place
    python scripts/set_cutoff.py 2015 --check    # show what would change, write nothing

CUTOFF_YEAR is exclusive: evidence must be published BEFORE 1 January of that year.
Then run:  pytest -q   (tests/test_cutoff_consistency.py catches any file this script missed)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rules(y: int) -> dict[str, list[tuple[str, str]]]:
    prev = y - 1
    return {
        "agents/lab_director.yaml": [
            (r"clock set to \d{4}", f"clock set to {y}"),
            (r"pre-\d{4} evidence", f"pre-{y} evidence"),
            (r"cutoff_year \d{4}\.", f"cutoff_year {y}."),
            (r"cutoff_year: \d{4}", f"cutoff_year: {y}"),
        ],
        "README.md": [
            (r"clock set to \d{4}", f"clock set to {y}"),
            (
                (r"`CUTOFF_YEAR=\d{4}` is exclusive: evidence must be published before "
                 r"1 January \d{4} \(dated up to \d{4}-12-31\)"),
                (f"`CUTOFF_YEAR={y}` is exclusive: evidence must be published before "
                 f"1 January {y} (dated up to {prev}-12-31)"),
            ),
        ],
        "lab/__init__.py": [
            (r"CUTOFF_YEAR=\d{4} means publications dated up to and including \d{4}-12-31",
             f"CUTOFF_YEAR={y} means publications dated up to and including {prev}-12-31"),
            (r'"CUTOFF_YEAR", "\d{4}"', f'"CUTOFF_YEAR", "{y}"'),
        ],
        "lab/scoring.py": [(r"masked_drug_pool\(\d{4}\)", f"masked_drug_pool({y})")],
        "scripts/toy_loop.py": [
            (r'(search_literature\(".*?", )\d{4}\)', rf"\g<1>{y})"),
            (r"(find_gene_set\(term, )\d{4}\)", rf"\g<1>{y})"),
        ],
        "scripts/check_europepmc.py": [
            (r"\(default \d{4}\)", f"(default {y})"),
            (r"else \d{4}\n", f"else {y}\n"),
        ],
        ".env.example": [(r"CUTOFF_YEAR=\d{4}", f"CUTOFF_YEAR={y}")],
        "LIMITATIONS.md": [(r"cutoff \d{4} \(enforced", f"cutoff {y} (enforced")],
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1 or not re.fullmatch(r"\d{4}", args[0]):
        print(__doc__)
        return 2
    year = int(args[0])
    changed = missing = 0
    for rel, rule_list in rules(year).items():
        path = ROOT / rel
        if not path.exists():
            print(f"  skip    {rel} (file not found)")
            continue
        text = original = path.read_text()
        for pattern, repl in rule_list:
            text, n = re.subn(pattern, repl, text)
            if n == 0:
                missing += 1
                print(f"  WARNING {rel}: pattern not found: {pattern[:55]}")
        if text != original:
            changed += 1
            print(f"  {'would change' if check else 'updated'}  {rel}")
            if not check:
                path.write_text(text)
    verb = "would change" if check else "changed"
    print(f"\nCutoff {year} (publications up to {year - 1}-12-31): {changed} file(s) {verb}, "
          f"{missing} pattern(s) not found.")
    print("Reminder: re-pin ChEMBL and the pathway source to releases before 1 January "
          f"{year}, and update docs/cutoff-decision.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

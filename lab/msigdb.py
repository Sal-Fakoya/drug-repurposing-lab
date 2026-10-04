"""MSigDB v4.0 (May 2013, the last release before the 2015 cutoff) gene sets, as UniProt accessions.

Symbols are mapped with ChEMBL 19's own synonym table (lab.chembl.symbol_map), so the mapping is
dated July 2014. Gene sets are never edited by hand; the only rules are mechanical:
  - a symbol with exactly one accession maps to it;
  - an ambiguous symbol (alias of several genes) is excluded and counted, never guessed;
  - a symbol ChEMBL does not know is dropped and counted. ChEMBL knows only proteins that are
    compound targets, so no drug could overlap with it, but it does shrink the set and universe.
Every set gets a report row so the loss is visible.
"""
import re
from pathlib import Path

from lab import chembl

MSIGDB_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "msigdb"


def find_gmt(collection: str = "c2.cp", root: Path = MSIGDB_DIR) -> Path:
    """Locate e.g. c2.cp.v4.0.symbols.gmt anywhere under the unpacked archive."""
    hits = sorted(root.rglob(f"{collection}.v4.0.symbols.gmt"))
    if not hits:
        raise FileNotFoundError(f"{collection}.v4.0.symbols.gmt not found under {root}")
    return hits[0]


def read_gmt(path: Path) -> dict[str, list[str]]:
    """GMT is tab-separated: set name, description or URL, then the gene symbols."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        name, _desc, *genes = line.split("\t")
        out[name] = genes
    return out


def load_gene_sets(symbols: dict[str, set[str]], collection: str = "c2.cp",
                   path: Path | None = None) -> tuple[dict[str, set[str]], list[dict]]:
    """Return ({set_name: {accession}}, report). Sets with no mapped gene are left out of the dict.

    `symbols` comes from lab.chembl.symbol_map. The report has one row per set:
    set_name, n_symbols, n_mapped, n_ambiguous, n_unmapped.
    """
    sets, report = {}, []
    for name, genes in read_gmt(path or find_gmt(collection)).items():
        accs: set[str] = set()
        amb = unm = 0
        for g in genes:
            hit = symbols.get(g.strip().upper(), set())
            if len(hit) == 1:
                accs |= hit
            elif hit:
                amb += 1
            else:
                unm += 1
        if accs:
            sets[name] = accs
        report.append({"set_name": name, "n_symbols": len(genes), "n_mapped": len(genes) - amb - unm,
                       "n_ambiguous": amb, "n_unmapped": unm})
    return sets, report


# Pre-specified rule for mapping a hypothesis term to MSigDB v4.0 c2.cp gene sets, fixed in
# docs/cutoff-decision.md (amendment 2026-10-04) before any lab run on real data. Do not edit:
# a change needs a new RULE_VERSION and a new amendment.
RULE_VERSION = "c2cp-name-tokens-v1"
RULE_COLLECTION = "c2.cp"
RULE_STOPWORDS = frozenset({"SIGNALING", "SIGNALLING", "SIGNAL", "PATHWAY", "PATHWAYS", "THE",
                            "OF", "AND", "BY", "VIA", "IN"})


def _rule_tokens(text: str) -> list[str]:
    """Upper-case, split on non-alphanumerics, join a letter token with a following number token."""
    raw = re.findall(r"[A-Z0-9]+", text.upper())
    out: list[str] = []
    for tok in raw:
        if tok.isdigit() and out and out[-1].isalpha():
            out[-1] += tok  # IL 6 -> IL6, so "IL-6", "IL6" and REACTOME_IL_6_... agree
        else:
            out.append(tok)
    return out


def term_tokens(term: str) -> frozenset[str]:
    return frozenset(t for t in _rule_tokens(term) if t not in RULE_STOPWORDS)


def set_tokens(set_name: str) -> frozenset[str]:
    """The set name's tokens without its source prefix (BIOCARTA_, KEGG_, REACTOME_, PID_, ...)."""
    tokens = _rule_tokens(set_name.split("_", 1)[1] if "_" in set_name else set_name)
    return frozenset(t for t in tokens if t not in RULE_STOPWORDS)


def match_term(term: str, set_names) -> list[str]:
    """Gene sets whose name contains every token of the term, sorted. [] if the term has no token.

    No synonyms, no fuzzy matching, no manual additions: "interleukin 6" does not match IL6 sets.
    """
    wanted = term_tokens(term)
    if not wanted:
        return []
    return sorted(name for name in set_names if wanted <= set_tokens(name))


def load_from_snapshot(collection: str = "c2.cp") -> tuple[dict[str, set[str]], list[dict]]:
    """Convenience: map with the pinned ChEMBL 19 database."""
    return load_gene_sets(chembl.symbol_map(chembl.connect()), collection)

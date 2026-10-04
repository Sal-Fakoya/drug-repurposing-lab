"""The pre-specified term -> MSigDB c2.cp gene set rule (lab.msigdb, docs/cutoff-decision.md)."""
import functools
import re
from pathlib import Path

import pytest
from test_snapshot import _build

from lab import msigdb, snapshot, tools

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["BIOCARTA_IL6_PATHWAY", "PID_IL6_7PATHWAY", "REACTOME_IL_6_SIGNALING", "ST_STAT3_PATHWAY",
         "KEGG_JAK_STAT_SIGNALING_PATHWAY", "ST_JAK_STAT_PATHWAY", "BIOCARTA_MTOR_PATHWAY",
         "KEGG_MTOR_SIGNALING_PATHWAY", "REACTOME_MTORC1_MEDIATED_SIGNALLING",
         "BIOCARTA_IGF1MTOR_PATHWAY", "REACTOME_PI3K_AKT_ACTIVATION", "KEGG_TGF_BETA_SIGNALING_PATHWAY"]

# The lists recorded in docs/cutoff-decision.md ("MSigDB v4.0 pin") for the configured terms.
RECORDED = {
    "mtor signaling": ["BIOCARTA_IGF1MTOR_PATHWAY", "BIOCARTA_MTOR_PATHWAY",
                       "KEGG_MTOR_SIGNALING_PATHWAY", "PID_MTOR_4PATHWAY",
                       "REACTOME_ENERGY_DEPENDENT_REGULATION_OF_MTOR_BY_LKB1_AMPK",
                       "REACTOME_MTORC1_MEDIATED_SIGNALLING"],
    "IL-6 signaling": ["BIOCARTA_IL6_PATHWAY", "PID_IL6_7PATHWAY"],
    "jak-stat signaling": ["KEGG_JAK_STAT_SIGNALING_PATHWAY", "ST_JAK_STAT_PATHWAY"],
    "vegf signaling": ["BIOCARTA_VEGF_PATHWAY", "KEGG_VEGF_SIGNALING_PATHWAY",
                       "PID_VEGFR1_2_PATHWAY", "PID_VEGFR1_PATHWAY", "PID_VEGF_VEGFR_PATHWAY",
                       "REACTOME_VEGF_LIGAND_RECEPTOR_INTERACTIONS"],
}


@pytest.mark.parametrize("term, keyword", [
    ("IL-6 signaling", "IL6"),
    ("il 6", "IL6"),
    ("IL6", "IL6"),
    ("JAK-STAT signalling pathway", "JAK_STAT"),
    ("PI3K/AKT", "PI3K_AKT"),
    ("TGF-beta", "TGF_BETA"),
    ("interleukin-6", "INTERLEUKIN6"),
    ("signaling of the pathway", ""),
    ("", ""),
])
def test_term_keyword(term, keyword):
    assert msigdb.term_keyword(term) == keyword


@pytest.mark.parametrize("term, expected", [
    ("IL-6 signaling", ["BIOCARTA_IL6_PATHWAY", "PID_IL6_7PATHWAY"]),  # IL_6 does not contain IL6
    ("JAK-STAT", ["KEGG_JAK_STAT_SIGNALING_PATHWAY", "ST_JAK_STAT_PATHWAY"]),
    ("mTOR", ["BIOCARTA_IGF1MTOR_PATHWAY", "BIOCARTA_MTOR_PATHWAY", "KEGG_MTOR_SIGNALING_PATHWAY",
              "REACTOME_MTORC1_MEDIATED_SIGNALLING"]),             # substring: MTORC1, IGF1MTOR too
    ("PI3K/AKT", ["REACTOME_PI3K_AKT_ACTIVATION"]),
    ("PI3K/AKT/mTOR", []),                   # the whole keyword must appear in one name
    ("interleukin 6", []),                    # no synonyms
    ("KEGG", []),                             # the source prefix is not part of the name
    ("signaling pathway", []),                # nothing left after the stopwords
    ("", []),
])
def test_match_term(term, expected):
    assert msigdb.match_term(term, NAMES) == expected


def test_matching_ignores_input_order_and_returns_sorted_names():
    assert msigdb.match_term("mtor", list(reversed(NAMES))) == msigdb.match_term("mtor", NAMES)


def test_rule_is_the_one_written_in_the_decision_record():
    doc = (ROOT / "docs" / "cutoff-decision.md").read_text()
    assert f'RULE_VERSION = "{msigdb.RULE_VERSION}"' in doc and msigdb.RULE_COLLECTION == "c2.cp"
    assert "every `c2.cp` set whose name\n  contains MTOR, IL6, JAK_STAT or VEGF" in doc
    listed = re.search(r"3\. Drop these words: ([A-Z, \n]+)\.", doc).group(1)
    assert {w.strip() for w in listed.replace("\n", " ").split(",")} == set(msigdb.RULE_STOPWORDS)
    for sets in RECORDED.values():
        for name in sets:
            assert name in doc


def test_real_mode_find_gene_set_reads_the_snapshot_with_the_rule(tmp_path, monkeypatch):
    _build(tmp_path, "snaps")  # fixture snapshot: c2.cp holds SET_A (MTOR, FKBP1A)
    monkeypatch.setattr(tools, "MODE", "real")
    monkeypatch.setattr(snapshot, "load", functools.partial(snapshot.load, root=tmp_path / "snaps"))
    # SET_A without its prefix ("SET") is "A"
    assert tools.find_gene_set("A", 2015) == {"gene_set_ids": ["SET_A"], "rule": msigdb.RULE_VERSION}
    assert tools.find_gene_set("set", 2015)["gene_set_ids"] == []  # prefix only
    assert tools.find_gene_set("interleukin", 2015)["gene_set_ids"] == []


def test_toy_mode_is_unchanged():
    assert tools.find_gene_set("mtor", 2015) == {"gene_set_ids": ["GS_MTOR"]}
    assert tools.find_gene_set("unknown", 2015) == {"gene_set_ids": ["GS_NULL"]}


def test_insight_prompt_explains_the_rule_and_the_untestable_case():
    prompt = (ROOT / "agents" / "lab_director.yaml").read_text()
    assert "whose name contains your term" in prompt and "No synonyms" in prompt
    assert "set testable: false" in prompt


@pytest.mark.skipif(not (snapshot.SNAPSHOT_ROOT / "2015" / "manifest.json").exists(),
                    reason="real snapshot not built (python -m lab.snapshot)")
@pytest.mark.parametrize("term", sorted(RECORDED))
def test_real_configured_terms_reproduce_the_recorded_lists(term):
    assert msigdb.match_term(term, snapshot.load(2015).gene_sets["c2.cp"]) == RECORDED[term]

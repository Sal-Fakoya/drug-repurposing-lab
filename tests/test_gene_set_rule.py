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


@pytest.mark.parametrize("text, tokens", [
    ("IL-6 signaling", {"IL6"}),
    ("il 6", {"IL6"}),
    ("IL6", {"IL6"}),
    ("JAK-STAT signalling pathway", {"JAK", "STAT"}),
    ("PI3K/AKT", {"PI3K", "AKT"}),           # a token that already has digits is not merged
    ("TGF-beta", {"TGF", "BETA"}),
    ("signaling of the pathway", set()),
    ("", set()),
])
def test_term_tokens(text, tokens):
    assert msigdb.term_tokens(text) == tokens


def test_set_names_lose_their_source_prefix_and_merge_letter_number_splits():
    assert msigdb.set_tokens("REACTOME_IL_6_SIGNALING") == {"IL6"}
    assert msigdb.set_tokens("KEGG_JAK_STAT_SIGNALING_PATHWAY") == {"JAK", "STAT"}
    assert "KEGG" not in msigdb.set_tokens("KEGG_MTOR_SIGNALING_PATHWAY")


@pytest.mark.parametrize("term, expected", [
    ("IL-6 signaling", ["BIOCARTA_IL6_PATHWAY", "PID_IL6_7PATHWAY", "REACTOME_IL_6_SIGNALING"]),
    ("JAK-STAT", ["KEGG_JAK_STAT_SIGNALING_PATHWAY", "ST_JAK_STAT_PATHWAY"]),
    ("STAT", ["KEGG_JAK_STAT_SIGNALING_PATHWAY", "ST_JAK_STAT_PATHWAY"]),  # STAT3 is another token
    ("mTOR", ["BIOCARTA_MTOR_PATHWAY", "KEGG_MTOR_SIGNALING_PATHWAY"]),   # not MTORC1 or IGF1MTOR
    ("PI3K/AKT", ["REACTOME_PI3K_AKT_ACTIVATION"]),
    ("PI3K/AKT/mTOR", []),                   # every token must be in one set name
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
    listed = re.search(r"2\. Drop these words from both: ([A-Z, \n]+)\.", doc).group(1)
    assert {w.strip() for w in listed.replace("\n", " ").split(",")} == set(msigdb.RULE_STOPWORDS)


def test_real_mode_find_gene_set_reads_the_snapshot_with_the_rule(tmp_path, monkeypatch):
    _build(tmp_path, "snaps")  # fixture snapshot: c2.cp holds SET_A (MTOR, FKBP1A)
    monkeypatch.setattr(tools, "MODE", "real")
    monkeypatch.setattr(snapshot, "load", functools.partial(snapshot.load, root=tmp_path / "snaps"))
    assert tools.find_gene_set("set a", 2015) == {"gene_set_ids": [], "rule": msigdb.RULE_VERSION}
    # SET_A's tokens after the prefix ("SET") are {"A"}
    assert tools.find_gene_set("A", 2015) == {"gene_set_ids": ["SET_A"], "rule": msigdb.RULE_VERSION}
    assert tools.find_gene_set("interleukin", 2015)["gene_set_ids"] == []


def test_toy_mode_is_unchanged():
    assert tools.find_gene_set("mtor", 2015) == {"gene_set_ids": ["GS_MTOR"]}
    assert tools.find_gene_set("unknown", 2015) == {"gene_set_ids": ["GS_NULL"]}


def test_insight_prompt_explains_the_rule_and_the_untestable_case():
    prompt = (ROOT / "agents" / "lab_director.yaml").read_text()
    assert "every word of your" in prompt and "No synonyms" in prompt
    assert "set testable: false" in prompt


@pytest.mark.skipif(not (snapshot.SNAPSHOT_ROOT / "2015" / "manifest.json").exists(),
                    reason="real snapshot not built (python -m lab.snapshot)")
def test_real_configured_terms_map_as_disclosed():
    names = snapshot.load(2015).gene_sets["c2.cp"]
    assert msigdb.match_term("IL-6 signaling", names) == [
        "BIOCARTA_IL6_PATHWAY", "PID_IL6_7PATHWAY", "REACTOME_IL_6_SIGNALING"]
    assert msigdb.match_term("jak-stat signaling", names) == [
        "KEGG_JAK_STAT_SIGNALING_PATHWAY", "ST_JAK_STAT_PATHWAY"]
    assert msigdb.match_term("vegf signaling", names) == [
        "BIOCARTA_VEGF_PATHWAY", "KEGG_VEGF_SIGNALING_PATHWAY", "PID_VEGF_VEGFR_PATHWAY",
        "REACTOME_VEGF_LIGAND_RECEPTOR_INTERACTIONS"]
    assert msigdb.match_term("mtor signaling", names) == [
        "BIOCARTA_MTOR_PATHWAY", "KEGG_MTOR_SIGNALING_PATHWAY", "PID_MTOR_4PATHWAY",
        "REACTOME_ENERGY_DEPENDENT_REGULATION_OF_MTOR_BY_LKB1_AMPK"]

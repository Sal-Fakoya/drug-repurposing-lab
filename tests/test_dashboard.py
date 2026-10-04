"""Dashboard skeleton: banner always, SYNTHETIC when toy, escaped, offline, no secrets."""
import importlib.util
import re
from pathlib import Path

import pytest
from test_snapshot import _build

from lab import masking, snapshot

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("dashboard_build", ROOT / "dashboard" / "build.py")
dash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dash)

SALT = "SECRET-SALT-VALUE-1234567890"


def _real(tmp_path):
    _build(tmp_path, "snap")
    snap = snapshot.load(2015, tmp_path / "snap")
    masking.init(snap.drugs, {}, snap.drugs[0], snap.sha256, tmp_path / "eval", SALT)
    return tmp_path / "snap", tmp_path / "eval"


def _text(path):
    return Path(path).read_text(encoding="utf-8")


def test_toy_build_has_banner_and_synthetic_bar(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    assert dash.BANNER in page and dash.SYNTHETIC in page


def test_real_build_has_banner_but_no_synthetic_bar_and_shows_provenance(tmp_path):
    root, ev = _real(tmp_path)
    page = _text(dash.build(tmp_path / "i.html", "real", 2015, root, eval_dir=ev))
    assert dash.BANNER in page and dash.SYNTHETIC not in page
    assert "ChEMBL_19" in page and "MSigDB" in page and "Snapshot SHA-256" in page


def test_only_the_salt_fingerprint_is_shown(tmp_path):
    root, ev = _real(tmp_path)
    page = _text(dash.build(tmp_path / "i.html", "real", 2015, root, eval_dir=ev))
    assert masking.fingerprint(SALT) in page
    assert SALT not in page and "m_" not in page and "CHEMBL" not in page.replace("ChEMBL", "")


def test_real_build_fails_loudly_without_a_snapshot_or_with_an_edited_one(tmp_path):
    with pytest.raises(FileNotFoundError):
        dash.build(tmp_path / "i.html", "real", 2015, tmp_path / "none", eval_dir=tmp_path / "ev")
    root, ev = _real(tmp_path)
    (root / "2015" / "drug_pool.json").write_text("[]\n")
    with pytest.raises(ValueError, match="corrupt"):
        dash.build(tmp_path / "i.html", "real", 2015, root, eval_dir=ev)


def test_untrusted_text_is_escaped(tmp_path):
    lim = tmp_path / "L.md"
    lim.write_text('## Known <b>limits</b>\n- <script>alert(1)</script> "x" onload="y"\n')
    page = _text(dash.build(tmp_path / "i.html", "toy", limitations_path=lim))
    assert "<script" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<b>limits" not in page and "&lt;b&gt;limits" in page


def test_page_is_offline_and_scriptless(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    assert not re.search(r"https?://|<script|<link|<img[^>]+src=[\"']http", page)


def test_todo_lines_are_flagged_and_warned_about(tmp_path, capsys):
    lim = tmp_path / "L.md"
    lim.write_text("## Sources\n- TODO list them\n- done\n")
    page = _text(dash.build(tmp_path / "i.html", "toy", limitations_path=lim))
    assert page.count("to be completed") == 1
    assert "1 TODO line" in capsys.readouterr().err


def test_banner_matches_the_one_the_publish_tool_exports():
    tools = (ROOT / "lab" / "tools.py").read_text()
    assert "Agent-generated hypotheses. Not medical advice." in tools
    assert "Needs laboratory and clinical validation." in tools
    assert dash.BANNER == ("Agent-generated hypotheses. Not medical advice. "
                           "Needs laboratory and clinical validation.")


def test_build_output_is_git_ignored():
    assert "dashboard/out/" in (ROOT / ".gitignore").read_text().splitlines()


def test_banner_and_synthetic_bar_share_one_sticky_container(tmp_path):
    """Two separately sticky bars overlap and the banner scrolls out of view; one wrapper stays whole."""
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    wrapper = re.search(r'<header class="bars">(.*?)</header>', page, re.S).group(1)
    assert dash.BANNER in wrapper and dash.SYNTHETIC in wrapper
    assert ".bars{position:sticky" in page and ".bar{position:sticky" not in page


def _row(i, synthetic=False, kind="verdict", agent="analysis"):
    row = {"id": i, "kind": kind, "ts": "2026-10-04T00:00:00Z", "agent": agent, "payload": {"secret": "PAYLOAD-X"}}
    if synthetic is not None:
        row["synthetic"] = synthetic
    return row


def test_real_rows_with_no_synthetic_flag_show_no_bar(tmp_path):
    root, ev = _real(tmp_path)
    rows = [_row("hyp_001", False, "hypothesis"), _row("res_001", False, "result")]
    page = _text(dash.build(tmp_path / "i.html", "real", 2015, root, eval_dir=ev, rows=rows))
    assert dash.SYNTHETIC not in page and "2 loaded, 0 synthetic" in page


def test_one_synthetic_row_raises_the_page_wide_bar_and_is_tagged(tmp_path):
    root, ev = _real(tmp_path)
    rows = [_row("hyp_001", False, "hypothesis"), _row("res_001", True, "result")]
    page = _text(dash.build(tmp_path / "i.html", "real", 2015, root, eval_dir=ev, rows=rows))
    assert dash.SYNTHETIC in page and "2 loaded, 1 synthetic" in page
    assert page.count(dash.SYNTHETIC_TAG) == 1                     # only the synthetic row is tagged
    tagged = [r for r in page.split("<tr>") if dash.SYNTHETIC_TAG in r]
    assert len(tagged) == 1 and "res_001" in tagged[0] and "hyp_001" not in tagged[0]


def test_a_row_that_does_not_say_is_treated_as_synthetic(tmp_path):
    root, ev = _real(tmp_path)
    page = _text(dash.build(tmp_path / "i.html", "real", 2015, root, eval_dir=ev,
                            rows=[_row("res_009", None)]))
    assert dash.SYNTHETIC in page and "1 loaded, 1 synthetic" in page


def test_toy_mode_without_rows_still_shows_the_bar_and_no_row_table(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    assert dash.SYNTHETIC in page and "Ledger rows loaded" not in page


def test_only_envelope_fields_are_rendered_and_they_are_escaped(tmp_path):
    rows = [_row("<img src=x onerror=alert(1)>", True, "<b>kind</b>", agent="<script>")]
    page = _text(dash.build(tmp_path / "i.html", "toy", rows=rows))
    assert "PAYLOAD-X" not in page                                  # payload is never rendered
    assert "<img" not in page and "<b>kind" not in page and "<script" not in page
    assert "&lt;img" in page


def test_malformed_rows_fail_loudly(tmp_path):
    with pytest.raises(ValueError, match="id and a kind"):
        dash.build(tmp_path / "i.html", "toy", rows=[{"kind": "result"}])
    with pytest.raises(ValueError, match="id and a kind"):
        dash.build(tmp_path / "i.html", "toy", rows=["not a row"])


def test_cutoff_ruler_follows_the_cutoff_year(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy", cutoff=2013))
    assert "31 Dec 2012" in page and "Evidence stops at 31 December 2012" in page
    assert "31 Dec 2014" not in page and "Cutoff 2013" in page


def test_ruler_is_an_accessible_offline_image(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    svg = re.search(r"<svg.*?</svg>", page, re.S).group(0)
    assert 'role="img"' in svg and "<title" in svg and "xmlns" not in svg and "http" not in svg


def test_each_tab_has_its_own_pane(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    tabs = re.findall(r'<label for="(t\d)">', page)
    assert tabs == ["t1", "t2", "t3", "t4"]
    assert all(f'id="{t}"' in page for t in tabs) and page.count('class="sec pane"') == 4
    assert "<script" not in page


def test_both_analyses_get_a_panel_with_a_plain_empty_state(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    assert "Analysis 1" in page and "Analysis 2" in page
    assert page.count("No run loaded") == 3                      # masked view plus both analysis panels
    assert "sorry" not in page.lower()


def test_page_is_always_light_whatever_the_system_theme(tmp_path):
    page = _text(dash.build(tmp_path / "i.html", "toy"))
    assert "prefers-color-scheme" not in page and "color-scheme:light" in page
    assert "--paper:#FFFFFF" in page


def test_attribution_footer_and_no_gene_lists_on_the_page(tmp_path):
    """ChEMBL is CC BY-SA (attribute it); MSigDB is internal-use only (no gene sets in the output)."""
    root, ev = _real(tmp_path)
    snap = snapshot.load(2015, root)
    page = _text(dash.build(tmp_path / "i.html", "real", 2015, root, eval_dir=ev))
    assert "ChEMBL release 19" in page and "CC BY-SA 3.0" in page
    genes = {g for sets in snap.gene_sets.values() for s in sets.values() for g in s}
    genes |= {g for _, g in snap.links["curated+activity"]}
    assert genes and not [g for g in genes if g in page]
    assert not [n for sets in snap.gene_sets.values() for n in sets if n in page]


def test_make_index_shows_trail_and_target_rank_but_no_payload_secrets():
    spec = importlib.util.spec_from_file_location("make_index", ROOT / "dashboard" / "make_index.py")
    mi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mi)
    rows = [
        {"id": "hyp_001", "kind": "hypothesis", "payload": {"claim": "<b>IL-6</b> drives it", "confidence": 0.5}},
        {"id": "exp_001", "kind": "experiment_spec", "payload": {"hyp_id": "hyp_001", "method": "A"}},
        {"id": "res_001", "kind": "result", "payload": {"exp_id": "exp_001", "ranked_drugs": [{}, {}, {}]}},
        {"id": "ver_001", "kind": "verdict", "payload": {"hyp_id": "hyp_001", "verdict": "supported", "z": "3.2"}},
    ]
    ev = [{"res_id": "res_001", "target_drug_rank": 2.0}]
    trail, (a1, a2) = mi.trail_html(rows), mi.scored_html(rows, ev, "curated")
    assert "&lt;b&gt;IL-6" in trail and "supported (z=3.2)" in trail
    assert "2 of 3" in a1 and "Not run in this build" in a2
    assert "Not run in this build" in mi.scored_html(rows, ev, "curated+activity")[0]


def test_headline_chart_is_inline_svg_with_one_dot_per_result():
    spec = importlib.util.spec_from_file_location("make_index", ROOT / "dashboard" / "make_index.py")
    mi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mi)
    rows = [{"id": "exp_001", "kind": "experiment_spec", "payload": {"hyp_id": "h", "method": "A"}},
            {"id": "res_001", "kind": "result", "payload": {"exp_id": "exp_001", "ranked_drugs": [{}] * 100}}]
    html = mi.headline_html(rows, [{"res_id": "res_001", "target_drug_rank": 50.0}])
    assert html.count("<circle") == 1 and "<svg" in html and "http" not in html

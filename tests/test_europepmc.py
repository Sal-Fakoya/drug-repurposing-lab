"""Real-mode search_literature against mocked Europe PMC responses, and the method B HHV-8 flag."""
import io
import json
import urllib.error
import urllib.parse

import pytest

import lab
from lab import hhv8, ledger, scoring, tools, toy_data

LEAKY_FIELDS = {"citedByCount": 412, "meshHeadingList": {"meshHeading": []},
                "authorString": "Doe J.", "journalInfo": {"journal": {"title": "J"}},
                "keywordList": {"keyword": ["x"]}, "isOpenAccess": "Y"}


def _rec(pmid, date="2010-05-01", title="Castleman disease case", abstract="An abstract."):
    return {"id": pmid, "source": "MED", "pmid": pmid, "firstPublicationDate": date,
            "title": title, "abstractText": abstract, **LEAKY_FIELDS}


class FakeEuropePMC:
    """Serves pages keyed by cursorMark and records every request."""

    def __init__(self, pages, failures=()):
        self.pages = pages  # {cursor: (records, next_cursor)}
        self.failures = list(failures)  # exceptions to raise before answering
        self.urls = []

    def __call__(self, request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else request
        self.urls.append(url)
        if self.failures:
            raise self.failures.pop(0)
        cursor = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["cursorMark"][0]
        records, next_cursor = self.pages[cursor]
        body = {"hitCount": 999, "resultList": {"result": records}}
        if next_cursor is not None:
            body["nextCursorMark"] = next_cursor
        return io.BytesIO(json.dumps(body).encode())

    def params(self, i):
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.urls[i]).query)


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(tools, "MODE", "real")
    monkeypatch.setattr(lab, "MODE", "real")
    monkeypatch.setattr(tools.time, "sleep", lambda s: None)


def _serve(monkeypatch, pages, failures=()):
    fake = FakeEuropePMC(pages, failures)
    monkeypatch.setattr(tools.urllib.request, "urlopen", fake)
    return fake


# ---------- paging ----------

def test_pages_through_every_hit_with_cursor_mark(real_mode, monkeypatch):
    fake = _serve(monkeypatch, {
        "*": ([_rec("1"), _rec("2")], "c1"),
        "c1": ([_rec("3")], "c2"),
        "c2": ([_rec("4")], "c2"),  # same cursor back: the last page
    })
    out = tools.search_literature("castleman", 2015)
    assert [fake.params(i)["cursorMark"][0] for i in range(3)] == ["*", "c1", "c2"]
    assert len(out["evidence_ids"]) == 4 and out["n_retrieved"] == 4
    first = fake.params(0)
    assert first["query"][0] == "(castleman) AND (FIRST_PDATE:[1900-01-01 TO 2014-12-31])"
    assert first["resultType"][0] == "core" and first["format"][0] == "json"
    assert first["pageSize"][0] == str(tools.EUROPEPMC_PAGE_SIZE)


@pytest.mark.parametrize("last_page", [([], "c2"), ([_rec("3")], None)])
def test_stops_on_an_empty_page_or_a_missing_next_cursor(real_mode, monkeypatch, last_page):
    fake = _serve(monkeypatch, {"*": ([_rec("1"), _rec("2")], "c1"), "c1": last_page,
                                "c2": ([_rec("99")], None)})
    out = tools.search_literature("castleman", 2015)
    assert len(fake.urls) == 2
    assert len(out["evidence_ids"]) == 2 + len(last_page[0])


def test_max_records_caps_retrieval_and_stops_paging(real_mode, monkeypatch):
    fake = _serve(monkeypatch, {"*": ([_rec("1"), _rec("2")], "c1"),
                                "c1": ([_rec("3"), _rec("4")], "c2"),
                                "c2": ([_rec("5")], None)})
    out = tools.search_literature("castleman", 2015, max_records=3)
    assert out["n_retrieved"] == 3 and len(out["evidence_ids"]) == 3
    assert len(fake.urls) == 2


# ---------- what is kept ----------

def test_keeps_only_title_abstract_and_first_publication_date(real_mode, monkeypatch):
    long_abstract = "word " * 300
    _serve(monkeypatch, {"*": ([_rec("1", date="2012-03-04", title="T", abstract=long_abstract)],
                               None)})
    ev = ledger.get(tools.search_literature("castleman", 2015)["evidence_ids"][0])
    assert set(ev) == {"id", "kind", "source", "pmid", "pub_date", "title", "abstract", "snippet",
                       "entities", "retrieved_at", "hhv8_status", "hhv8_terms"}
    assert (ev["title"], ev["abstract"], ev["pub_date"]) == ("T", long_abstract, "2012-03-04")
    assert ev["snippet"] == long_abstract[:600] and ev["entities"] == []
    assert not set(LEAKY_FIELDS) & set(ev)
    assert "412" not in json.dumps(ledger._find(ev["id"]))


@pytest.mark.parametrize("date", ["2015-01-01", "2016-07-07", "", None, "n.d.", "15-01-2014"])
def test_drops_records_on_or_after_the_cutoff_or_without_a_usable_date(real_mode, monkeypatch,
                                                                       date):
    _serve(monkeypatch, {"*": ([_rec("1", date="2014-12-31"), _rec("2", date=date)], None)})
    ids = tools.search_literature("castleman", 2015)["evidence_ids"]
    assert [ledger.get(i)["pmid"] for i in ids] == ["1"]


def test_a_pmid_seen_twice_is_stored_once(real_mode, monkeypatch):
    _serve(monkeypatch, {"*": ([_rec("1"), _rec("1")], "c1"), "c1": ([_rec("1")], None)})
    out = tools.search_literature("castleman", 2015)
    again = tools.search_literature("castleman", 2015)
    assert out["evidence_ids"] == again["evidence_ids"] == ["ev_001"]
    assert len(ledger.rows_of_kind("evidence_record")) == 1


def test_records_are_written_by_the_literature_agent_and_not_synthetic(real_mode, monkeypatch):
    _serve(monkeypatch, {"*": ([_rec("1")], None)})
    row = ledger._find(tools.search_literature("castleman", 2015)["evidence_ids"][0])
    assert row["agent"] == "literature" and row["synthetic"] is False


# ---------- HHV-8 status ----------

NEGATIONS = [  # every negation form the status rule accepts
    ("HHV-8-negative", ["HHV-8"]),
    ("HHV-8 negative", ["HHV-8"]),
    ("negative for HHV-8", ["HHV-8"]),
    ("HHV-8-seronegative", ["HHV-8"]),
    ("HHV-8 seronegative", ["HHV-8"]),
    ("HIV-negative", ["HIV"]),
    ("HIV-1-negative", ["HIV"]),
    ("seronegative for HHV-8/HIV", ["HHV-8", "HIV"]),
    ("seronegative for HHV-8 and HIV", ["HHV-8", "HIV"]),
    ("seronegative for HIV", ["HIV"]),
    ("negative for both HHV-8 and HIV", ["HHV-8", "HIV"]),
    ("HHV-8 and HIV negative", ["HHV-8", "HIV"]),
    ("HHV8-negative", ["HHV-8"]),
    ("KSHV-negative", ["KSHV"]),
    ("Kaposi sarcoma-associated herpesvirus (KSHV)-negative", ["KSHV"]),
    ("human herpesvirus 8 (HHV-8)-negative", ["HHV-8"]),
    ("no evidence of HHV-8", ["HHV-8"]),
    ("no evidence of HHV-8 or HIV", ["HHV-8", "HIV"]),
    ("HHV-8 PCR negative", ["HHV-8"]),
    ("HHV-8 PCR was negative", ["HHV-8"]),
    ("HHV-8 was not detected", ["HHV-8"]),
    ("HIV and HHV-8 were not detected", ["HHV-8", "HIV"]),
    ("LANA-1 negative", ["HHV-8"]),
    ("LANA-1-negative", ["HHV-8"]),
    ("negative for LANA-1", ["HHV-8"]),
    ("absence of HHV-8", ["HHV-8"]),
    ("absence of KSHV and HIV", ["KSHV", "HIV"]),
]


@pytest.mark.parametrize("phrase, terms", NEGATIONS)
def test_each_negation_pattern_is_negated_only(phrase, terms):
    title = f"{phrase} idiopathic multicentric Castleman disease"
    assert hhv8.classify(title, "IL-6 was elevated.") == ("negated_only", terms)


@pytest.mark.parametrize("phrase", [p for p, _ in NEGATIONS])
def test_a_negation_plus_a_positive_finding_counts_as_positive(phrase):
    status, _ = hhv8.classify(f"Patient 1 was {phrase}.",
                              "In patient 2, HHV-8 DNA was detected and Kaposi sarcoma developed.")
    assert status == "positive"


@pytest.mark.parametrize("title, abstract, terms", [
    ("HHV-8-associated multicentric Castleman disease", "", ["HHV-8"]),
    ("HHV-8-positive MCD", "", ["HHV-8"]),
    ("Castleman disease", "HHV8 DNA was detected.", ["HHV-8"]),
    ("Castleman disease", "Human herpesvirus 8 latency.", ["HHV-8"]),
    ("Castleman disease", "human herpes virus-8 serology", ["HHV-8"]),
    ("KSHV-encoded viral IL-6", "", ["KSHV"]),
    ("Castleman disease and Kaposi's sarcoma", "", ["Kaposi"]),
    ("Castleman disease", "Patients were HIV-positive.", ["HIV"]),
    ("Castleman disease in HIV-infected patients", "", ["HIV"]),
    ("Castleman disease", "LANA-1-positive plasmablasts were seen.", ["HHV-8"]),
    ("Castleman disease", "HHV-8 PCR was positive.", ["HHV-8"]),
    # a negation of something else does not negate a later HHV-8 finding
    ("Castleman disease", "No evidence of lymphoma; HHV-8-associated MCD.", ["HHV-8"]),
    # not one of the negation forms, so it stays positive (the exclusion run drops it)
    ("Castleman disease", "HHV-8 serology was unremarkable.", ["HHV-8"]),
])
def test_present_or_causal_mentions_are_positive(title, abstract, terms):
    assert hhv8.classify(title, abstract) == ("positive", terms)


@pytest.mark.parametrize("title, abstract", [
    ("Idiopathic multicentric Castleman disease", "IL-6 was elevated in an archive of hives."),
    ("Castleman disease", ""),
    ("", ""),
])
def test_no_mention_is_none(title, abstract):
    assert hhv8.classify(title, abstract) == ("none", [])


def test_search_stores_status_and_terms_and_reports_counts(real_mode, monkeypatch):
    _serve(monkeypatch, {"*": ([
        _rec("1", title="KSHV-associated MCD"),
        _rec("2", title="HHV-8-negative idiopathic MCD", abstract="HIV-negative patients."),
        _rec("3", title="HHV-8-negative MCD", abstract="One patient developed Kaposi sarcoma."),
        _rec("4", title="Idiopathic MCD", abstract="IL-6 blockade."),
    ], None)})
    out = tools.search_literature("castleman", 2015)
    stored = [ledger.get(i) for i in out["evidence_ids"]]
    assert [(e["hhv8_status"], e["hhv8_terms"]) for e in stored] == [
        ("positive", ["KSHV"]), ("negated_only", ["HHV-8", "HIV"]),
        ("positive", ["HHV-8", "Kaposi"]), ("none", [])]
    assert out["hhv8_status_counts"] == {"positive": 2, "negated_only": 1, "none": 1}
    assert all("hhv8_related" not in e for e in stored)


# ---------- failures ----------

def test_transient_failures_are_retried(real_mode, monkeypatch):
    fake = _serve(monkeypatch, {"*": ([_rec("1")], None)}, failures=[
        TimeoutError("read timed out"),
        urllib.error.HTTPError("u", 503, "busy", None, None),
        urllib.error.URLError("connection reset")])
    assert len(tools.search_literature("castleman", 2015)["evidence_ids"]) == 1
    assert len(fake.urls) == 4


def test_client_errors_are_not_retried(real_mode, monkeypatch):
    fake = _serve(monkeypatch, {}, failures=[urllib.error.HTTPError("u", 400, "bad", None, None)])
    with pytest.raises(RuntimeError, match="HTTP 400"):
        tools.search_literature("castleman", 2015)
    assert len(fake.urls) == 1


def test_gives_up_after_the_retry_budget(real_mode, monkeypatch):
    errors = [urllib.error.URLError("down")] * tools.EUROPEPMC_RETRIES
    fake = _serve(monkeypatch, {}, failures=errors)
    with pytest.raises(RuntimeError, match="failed after"):
        tools.search_literature("castleman", 2015)
    assert len(fake.urls) == tools.EUROPEPMC_RETRIES
    assert ledger.rows_of_kind("evidence_record") == []


def test_cutoff_guard_still_applies_before_any_request(real_mode, monkeypatch):
    fake = _serve(monkeypatch, {})
    with pytest.raises(ValueError):
        tools.search_literature("castleman", 2016)
    assert fake.urls == []


# ---------- method B with and without HHV-8-related records ----------

def _scores(**kw):
    pool = scoring.masked_drug_pool(2015)
    ranked = scoring.literature_graph(pool, ["GS_IL6", "GS_MTOR"], 2015, seed=0, **kw)
    return {r["drug_id"]: r["score"] for r in ranked}


def test_method_b_default_is_unchanged_and_excluding_hhv8_only_removes_counts():
    with_hhv8, default, without = _scores(include_hhv8=True), _scores(), _scores(include_hhv8=False)
    assert with_hhv8 == default
    assert all(without[d] <= with_hhv8[d] for d in with_hhv8)
    assert any(without[d] < with_hhv8[d] for d in with_hhv8)
    part, (_, total) = toy_data.hhv8_positive_comentions(), toy_data.build()
    assert all(0 <= part[k] <= total[k] for k in total)


def _hyp():
    ev = tools.search_literature("q", 2015)["evidence_ids"]
    return tools.write_ledger("hypothesis", {
        "claim": "IL-6", "evidence_ids": ev, "confidence": 0.5, "status": "active",
        "gene_set_ids": ["GS_IL6"], "predicted_direction": "enriched"}, agent="insight")["id"]


def _spec(hid, **params):
    return tools.write_ledger("experiment_spec", {
        "hyp_id": hid, "method": "B", "arm_id": f"{hid}:B",
        "params": {"gene_set_ids": ["GS_IL6"], **params}, "expected_cost": 2.0,
        "expected_learning": 1.0, "feasibility": 1.0}, agent="planner")["id"]


def test_run_experiment_honours_the_spec_flag_and_both_variants_can_run():
    hid = _hyp()
    with_id = tools.run_experiment(_spec(hid))["res_id"]
    without_id = tools.run_experiment(_spec(hid, include_hhv8=False))["res_id"]
    pool = scoring.masked_drug_pool(2015)
    assert ledger.get(with_id)["ranked_drugs"] == scoring.literature_graph(
        pool, ["GS_IL6"], 2015, seed=0)
    assert ledger.get(without_id)["ranked_drugs"] == scoring.literature_graph(
        pool, ["GS_IL6"], 2015, seed=0, include_hhv8=False)
    assert ledger.get(with_id)["ranked_drugs"] != ledger.get(without_id)["ranked_drugs"]


@pytest.mark.parametrize("env, expected", [(None, None), ("1", None), ("0", False),
                                           ("false", False)])
def test_planner_records_the_hhv8_choice_on_method_b_specs_only(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("LAB_METHOD_B_INCLUDE_HHV8", raising=False)
    else:
        monkeypatch.setenv("LAB_METHOD_B_INCLUDE_HHV8", env)
    _hyp()
    arms = {a["arm_id"]: a["params"] for a in ledger.active_arms()}
    for arm_id, params in arms.items():
        if arm_id.endswith(":B") and expected is not None:
            assert params["include_hhv8"] is False
        else:
            assert "include_hhv8" not in params


def test_real_method_b_still_needs_its_loader(real_mode, monkeypatch):
    monkeypatch.setattr(scoring, "MODE", "real")
    with pytest.raises(NotImplementedError):
        scoring.literature_graph([], ["GS_IL6"], 2015, include_hhv8=False)

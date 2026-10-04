"""Masking: opaque, unordered, one-to-one, fail-closed, and the secret stays out of git."""
import json
import os
import re
from pathlib import Path

import pytest
from test_chembl import _db

from lab import masking, snapshot

DRUGS = [f"CHEMBL{i}" for i in range(1, 401)]
NAMES = {"CHEMBL1": "sirolimus", "CHEMBL2": "other"}


def _snap(drugs=("CHEMBL1", "CHEMBL2", "CHEMBL3")):
    links = {"curated": [("CHEMBL1", "P62942"), ("CHEMBL2", "P05231")],
             "curated+activity": [("CHEMBL1", "P62942"), ("CHEMBL1", "P42345")]}
    return snapshot.Snapshot(2015, "h" * 64, list(drugs), links, {}, {})


def _init(tmp_path, salt="test-salt", **kw):
    snap = _snap()
    masking.init(snap.drugs, NAMES, "CHEMBL1", snap.sha256, tmp_path, salt, **kw)
    return snap, masking.load(tmp_path)


def test_ids_are_opaque_and_deterministic():
    a, b = masking.masked_id("s", "CHEMBL413"), masking.masked_id("s", "CHEMBL413")
    assert a == b and re.fullmatch(r"m_[0-9a-f]{10}", a)
    assert masking.masked_id("other-salt", "CHEMBL413") != a


def test_masked_order_carries_no_chembl_order():
    ids = [masking.masked_id("test-salt", d) for d in DRUGS]
    ranks = sorted(range(len(ids)), key=ids.__getitem__)          # position of each drug after sorting
    n = len(ids)
    mean = (n - 1) / 2
    cov = sum((i - mean) * (r - mean) for i, r in enumerate(ranks))
    var = sum((i - mean) ** 2 for i in range(n))
    assert abs(cov / var) < 0.2                                   # Spearman-style: no ordering signal


def test_round_trip_names_and_target(tmp_path):
    _, m = _init(tmp_path)
    mid = m.mask("CHEMBL1")
    assert m.unmask(mid) == "CHEMBL1" and m.display_name(mid) == "sirolimus"
    assert m.target_masked_id == mid
    assert m.display_name(m.mask("CHEMBL3")) == "CHEMBL3"         # unnamed drug falls back to its id
    with pytest.raises(ValueError, match="unknown"):
        m.unmask("m_0000000000")


def test_masked_pool_matches_snapshot_without_leaking_real_ids(tmp_path):
    snap, m = _init(tmp_path)
    pool = m.masked_pool(snap, "curated+activity")
    assert [p["drug_id"] for p in pool] == sorted(p["drug_id"] for p in pool)
    by_real = {m.unmask(p["drug_id"]): p["targets"] for p in pool}
    assert by_real == {p["drug_id"]: p["targets"] for p in snap.pool("curated+activity")}
    assert "CHEMBL" not in json.dumps(pool)


def test_pool_with_a_drug_missing_from_the_mask_is_refused(tmp_path):
    _, m = _init(tmp_path)
    with pytest.raises(ValueError, match="re-run init"):
        m.masked_pool(_snap(drugs=("CHEMBL1", "CHEMBL2", "CHEMBL3", "CHEMBL9")))


def test_collision_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(masking, "ID_HEX", 1)                      # 16 possible ids for 400 drugs
    with pytest.raises(ValueError, match="collision"):
        masking.init(DRUGS, {}, "CHEMBL1", "h", tmp_path, "s")


def test_existing_mask_is_not_overwritten_without_force(tmp_path):
    _init(tmp_path)
    with pytest.raises(FileExistsError):
        _init(tmp_path)
    _, m = _init(tmp_path, salt="new-salt", force=True)
    assert m.mask("CHEMBL1") != masking.masked_id("test-salt", "CHEMBL1")


def test_missing_files_fail_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="lab.masking"):
        masking.load(tmp_path)
    _init(tmp_path)
    (tmp_path / "names.json").unlink()
    with pytest.raises(FileNotFoundError):
        masking.load(tmp_path)


def test_target_must_be_in_the_pool(tmp_path):
    with pytest.raises(ValueError, match="not in the drug pool"):
        masking.init(["CHEMBL1"], {}, "CHEMBL9", "h", tmp_path, "s")


@pytest.mark.skipif(os.name == "nt", reason="Windows does not enforce Unix mode bits")
def test_files_and_folder_are_owner_only(tmp_path):
    _init(tmp_path)
    assert tmp_path.stat().st_mode & 0o077 == 0
    for f in ("mask.json", "names.json", "target.json"):
        assert (tmp_path / f).stat().st_mode & 0o077 == 0


def test_fingerprint_hides_the_salt():
    fp = masking.fingerprint("test-salt")
    assert re.fullmatch(r"[0-9a-f]{8}", fp) and "test-salt" not in fp


def test_init_from_snapshot_finds_target_by_name_not_by_typed_id(tmp_path):
    conn = _db()
    conn.execute("UPDATE molecule_dictionary SET pref_name = 'Sirolimus' WHERE chembl_id = 'CHEMBL1'")
    snap = _snap(drugs=("CHEMBL1", "CHEMBL4"))
    masking.init_from_snapshot(snap, conn, tmp_path, salt="s")
    assert masking.load(tmp_path).target_chembl_id == "CHEMBL1"
    conn.execute("UPDATE molecule_dictionary SET pref_name = 'sirolimus' WHERE chembl_id = 'CHEMBL4'")
    with pytest.raises(ValueError, match="exactly one"):
        masking.init_from_snapshot(snap, conn, tmp_path / "x", salt="s")


def test_eval_only_folder_is_git_ignored():
    root = Path(masking.__file__).resolve().parent.parent
    assert "data/eval_only/" in (root / ".gitignore").read_text().splitlines()


# ---- restore: a second machine gets the same ids from the same mask.json ----

def _conn_with_target():
    conn = _db()
    conn.execute("UPDATE molecule_dictionary SET pref_name = 'sirolimus' WHERE chembl_id = 'CHEMBL1'")
    return conn


def _sender_and_receiver(tmp_path, receiver_drugs=("CHEMBL1", "CHEMBL4")):
    snap = _snap(drugs=("CHEMBL1", "CHEMBL4"))
    masking.init_from_snapshot(snap, _conn_with_target(), tmp_path / "A", salt="shared-salt")
    (tmp_path / "B").mkdir()
    (tmp_path / "B" / "mask.json").write_bytes((tmp_path / "A" / "mask.json").read_bytes())
    return snap, _snap(drugs=receiver_drugs)


def test_restore_gives_the_receiver_identical_ids_without_touching_the_salt(tmp_path):
    _, snap_b = _sender_and_receiver(tmp_path)
    before = (tmp_path / "B" / "mask.json").read_bytes()
    fp = masking.restore_from_snapshot(snap_b, _conn_with_target(), tmp_path / "B")
    a, b = masking.load(tmp_path / "A"), masking.load(tmp_path / "B")
    assert (tmp_path / "B" / "mask.json").read_bytes() == before                # salt never changes
    assert fp == a.fingerprint == b.fingerprint
    assert [b.mask(d) for d in ("CHEMBL1", "CHEMBL4")] == [a.mask(d) for d in ("CHEMBL1", "CHEMBL4")]
    assert b.target_masked_id == a.target_masked_id and b.names == a.names


def test_restore_refuses_a_mask_made_for_a_different_snapshot_and_writes_nothing(tmp_path):
    _, other = _sender_and_receiver(tmp_path, receiver_drugs=("CHEMBL1", "CHEMBL3"))
    with pytest.raises(ValueError, match="does not match this snapshot"):
        masking.restore_from_snapshot(other, _conn_with_target(), tmp_path / "B")
    assert sorted(p.name for p in (tmp_path / "B").iterdir()) == ["mask.json"]


def test_restore_refuses_a_corrupted_mask(tmp_path):
    _, snap_b = _sender_and_receiver(tmp_path)
    m = json.loads((tmp_path / "B" / "mask.json").read_text())
    m["salt"] = "someone-elses-salt"
    (tmp_path / "B" / "mask.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="does not match this snapshot"):
        masking.restore_from_snapshot(snap_b, _conn_with_target(), tmp_path / "B")


def test_restore_will_not_overwrite_without_force(tmp_path):
    _, snap_b = _sender_and_receiver(tmp_path)
    masking.restore_from_snapshot(snap_b, _conn_with_target(), tmp_path / "B")
    with pytest.raises(FileExistsError, match="--force"):
        masking.restore_from_snapshot(snap_b, _conn_with_target(), tmp_path / "B")
    masking.restore_from_snapshot(snap_b, _conn_with_target(), tmp_path / "B", force=True)


def test_restore_without_mask_json_says_not_to_run_init(tmp_path):
    with pytest.raises(FileNotFoundError, match="do NOT run init"):
        masking.restore_from_snapshot(_snap(), _conn_with_target(), tmp_path / "empty")


def test_command_line_restore_prints_the_fingerprint_but_never_the_salt(tmp_path, monkeypatch, capsys):
    _, snap_b = _sender_and_receiver(tmp_path)
    monkeypatch.setattr(masking, "EVAL_DIR", tmp_path / "B")
    monkeypatch.setattr(masking.snapshot_mod, "load", lambda: snap_b)
    monkeypatch.setattr("lab.chembl.connect", _conn_with_target)
    masking.main(["restore"])
    out = capsys.readouterr().out
    assert masking.fingerprint("shared-salt") in out and "shared-salt" not in out
    assert masking.load(tmp_path / "B").target_chembl_id == "CHEMBL1"


def test_command_line_init_still_refuses_to_replace_an_existing_mask(tmp_path, monkeypatch):
    snap, _ = _sender_and_receiver(tmp_path)
    monkeypatch.setattr(masking, "EVAL_DIR", tmp_path / "A")
    monkeypatch.setattr(masking.snapshot_mod, "load", lambda: snap)
    monkeypatch.setattr("lab.chembl.connect", _conn_with_target)
    with pytest.raises(FileExistsError):
        masking.main(["init"])

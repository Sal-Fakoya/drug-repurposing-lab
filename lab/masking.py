"""Masked drug ids: agents and scoring see opaque ids, never ChEMBL ids or names.

masked id = "m_" + first ID_HEX hex digits of HMAC-SHA256(salt, chembl_id). Opaque, deterministic
for a given salt, and unordered (ChEMBL ids rise roughly with registration date, so an id that
sorted like them would leak). The salt is a secret: it lives only in data/eval_only/ (git-ignored),
which no agent tool may read.

  data/eval_only/mask.json    {"salt", "snapshot_sha256", "map": {masked: chembl_id}}
  data/eval_only/names.json   {chembl_id: display name}   used only to publish an approved ranking
  data/eval_only/target.json  {"target_chembl_id": ...}   the pre-registered target drug

Create them once with `python -m lab.masking`. Set LAB_EVAL_DIR to keep them outside the repo, on a
filesystem that enforces owner-only permissions (the files are chmod 600). A different salt gives different ids for every drug,
so share mask.json (privately, not via git) to get identical ids on two machines.
"""
import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from lab import snapshot as snapshot_mod

# LAB_EVAL_DIR moves the secret off a filesystem that ignores file modes (e.g. NTFS/FAT mounts).
EVAL_DIR = Path(os.environ.get("LAB_EVAL_DIR") or Path(__file__).resolve().parent.parent / "data" / "eval_only")
ID_HEX = 10          # 40 bits: collisions among ~2000 drugs are ~1e-6, and init() checks anyway
TARGET_NAME = "sirolimus"   # the pre-registered target drug (docs/cutoff-decision.md)


def masked_id(salt: str, chembl_id: str) -> str:
    return "m_" + hmac.new(salt.encode(), chembl_id.encode(), hashlib.sha256).hexdigest()[:ID_HEX]


def _write_private(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=1) + "\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)    # best effort on filesystems that honour modes


def init(drugs: list[str], names: dict[str, str], target_chembl_id: str, snapshot_sha256: str,
         eval_dir: Path = EVAL_DIR, salt: str | None = None, force: bool = False) -> str:
    """Write the eval-only files and return the salt fingerprint. Refuses to replace an existing mask.

    Replacing the salt silently renames every drug, which would orphan every ledger row, so it needs
    force=True.
    """
    eval_dir = Path(eval_dir)
    if (eval_dir / "mask.json").exists() and not force:
        raise FileExistsError(f"{eval_dir / 'mask.json'} exists; pass force=True to rotate the salt")
    if target_chembl_id not in drugs:
        raise ValueError(f"target {target_chembl_id} is not in the drug pool")
    salt = salt or secrets.token_hex(32)
    mapping = {masked_id(salt, d): d for d in drugs}
    if len(mapping) != len(set(drugs)):
        raise ValueError("masked id collision: raise ID_HEX")
    eval_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.chmod(stat.S_IRWXU)
    _write_private(eval_dir / "mask.json", {"salt": salt, "snapshot_sha256": snapshot_sha256, "map": mapping})
    _write_private(eval_dir / "names.json", {d: names.get(d) or d for d in drugs})
    _write_private(eval_dir / "target.json", {"target_chembl_id": target_chembl_id})
    return fingerprint(salt)


def fingerprint(salt: str) -> str:
    """Short, non-reversible tag of the salt for ledger rows. Safe to log."""
    return hashlib.sha256(salt.encode()).hexdigest()[:8]


@dataclass(frozen=True)
class Mask:
    salt: str
    to_chembl: dict[str, str]
    names: dict[str, str]
    target_chembl_id: str

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.salt)

    def mask(self, chembl_id: str) -> str:
        return masked_id(self.salt, chembl_id)

    def unmask(self, mid: str) -> str:
        if mid not in self.to_chembl:
            raise ValueError(f"unknown masked id {mid!r}")
        return self.to_chembl[mid]

    def display_name(self, mid: str) -> str:
        """Human-readable name, for publishing an approved ranking only."""
        return self.names[self.unmask(mid)]

    @property
    def target_masked_id(self) -> str:
        return self.mask(self.target_chembl_id)

    def masked_pool(self, snap: snapshot_mod.Snapshot, definition: str = "curated") -> list[dict]:
        """The snapshot pool with real ids replaced by masked ids, ordered by masked id."""
        pool = snap.pool(definition)
        unknown = [p["drug_id"] for p in pool if self.mask(p["drug_id"]) not in self.to_chembl]
        if unknown:
            raise ValueError(f"{len(unknown)} drugs are not in mask.json: re-run init for this snapshot")
        return sorted(({"drug_id": self.mask(p["drug_id"]), "targets": p["targets"]} for p in pool),
                      key=lambda p: p["drug_id"])


def load(eval_dir: Path = EVAL_DIR) -> Mask:
    """Read the eval-only files. Fails closed if any is missing."""
    eval_dir = Path(eval_dir)
    try:
        m = json.loads((eval_dir / "mask.json").read_text())
        names = json.loads((eval_dir / "names.json").read_text())
        target = json.loads((eval_dir / "target.json").read_text())["target_chembl_id"]
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{exc.filename} missing: run `python -m lab.masking` first") from exc
    return Mask(m["salt"], m["map"], names, target)


def init_from_snapshot(snap: snapshot_mod.Snapshot, conn, eval_dir: Path = EVAL_DIR,
                       salt: str | None = None, force: bool = False) -> str:
    """Names and the target id come from the pinned ChEMBL 19 database (found by name, not typed in)."""
    rows = dict(conn.execute("SELECT chembl_id, pref_name FROM molecule_dictionary"))
    target = [c for c, n in rows.items() if (n or "").lower() == TARGET_NAME and c in snap.drugs]
    if len(target) != 1:
        raise ValueError(f"expected exactly one approved parent named {TARGET_NAME!r}, got {target}")
    return init(snap.drugs, {d: (rows.get(d) or "") for d in snap.drugs}, target[0], snap.sha256,
                eval_dir, salt, force)


if __name__ == "__main__":
    from lab import chembl
    if os.environ.get("MASK_FORCE") == "1":
        print("rotating the salt: every masked id changes")
    fp = init_from_snapshot(snapshot_mod.load(), chembl.connect(), force=os.environ.get("MASK_FORCE") == "1")
    print(f"wrote {EVAL_DIR}  salt fingerprint {fp}  (the salt itself is never printed)")

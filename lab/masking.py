"""Masked drug ids: agents and scoring see opaque ids, never ChEMBL ids or names.

masked id = "m_" + first ID_HEX hex digits of HMAC-SHA256(salt, chembl_id). Opaque, deterministic
for a given salt, and unordered (ChEMBL ids rise roughly with registration date, so an id that
sorted like them would leak). The salt is a secret that no agent tool may read. It lives in the
eval folder, by default ~/.drug_lab_eval (override with LAB_EVAL_DIR):

  <eval folder>/mask.json    {"salt", "snapshot_sha256", "map": {masked: chembl_id}}
  <eval folder>/names.json   {chembl_id: display name}   used only to publish an approved ranking
  <eval folder>/target.json  {"target_chembl_id": ...}   the pre-registered target drug

First time, on ONE machine:  python -m lab.masking          (init: makes the salt)
Every other machine: copy the mask.json you were sent (privately, never via git) into the eval
folder, then  python -m lab.masking restore.  Never run init there: a second salt gives different
masked ids for every drug, so `init` refuses if a mask.json already exists at any known location.
The files are chmod 600; keep the folder on a filesystem that enforces modes.
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

# The secret lives OUTSIDE the repo by default, in ~/.drug_lab_eval, on a filesystem that enforces
# file modes (a /mnt or NTFS/FAT mount ignores chmod). LAB_EVAL_DIR overrides it. The old in-repo
# folder is only checked, so `init` can refuse to create a second salt next to an existing one.
HOME_DIR = Path.home() / ".drug_lab_eval"
LEGACY_DIR = Path(__file__).resolve().parent.parent / "data" / "eval_only"


def default_eval_dir(environ=os.environ) -> Path:
    return Path(environ.get("LAB_EVAL_DIR") or HOME_DIR)


EVAL_DIR = default_eval_dir()
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
    force=True, and even then the old mask.json is kept as mask.<fingerprint>.bak.json first, so a
    shared salt can never be lost by a rotation.
    """
    eval_dir = Path(eval_dir)
    if (eval_dir / "mask.json").exists():
        if not force:
            raise FileExistsError(f"{eval_dir / 'mask.json'} exists; pass force=True (CLI: --force) to rotate the salt")
        backup_mask(eval_dir)
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


def backup_mask(eval_dir: Path) -> Path | None:
    """Copy an existing mask.json to mask.<fingerprint>.bak.json (owner-only). None if there is none."""
    src = Path(eval_dir) / "mask.json"
    if not src.exists():
        return None
    old = json.loads(src.read_text())
    dest = Path(eval_dir) / f"mask.{fingerprint(old['salt'])}.bak.json"
    _write_private(dest, old)
    return dest


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


def _names_and_target(snap: snapshot_mod.Snapshot, conn) -> tuple[dict[str, str], str]:
    """Names and the target id come from the pinned ChEMBL 19 database (found by name, not typed in)."""
    rows = dict(conn.execute("SELECT chembl_id, pref_name FROM molecule_dictionary"))
    target = [c for c, n in rows.items() if (n or "").lower() == TARGET_NAME and c in snap.drugs]
    if len(target) != 1:
        raise ValueError(f"expected exactly one approved parent named {TARGET_NAME!r}, got {target}")
    return {d: (rows.get(d) or "") for d in snap.drugs}, target[0]


def init_from_snapshot(snap: snapshot_mod.Snapshot, conn, eval_dir: Path = EVAL_DIR,
                       salt: str | None = None, force: bool = False) -> str:
    names, target = _names_and_target(snap, conn)
    return init(snap.drugs, names, target, snap.sha256, eval_dir, salt, force)


def restore_from_snapshot(snap: snapshot_mod.Snapshot, conn, eval_dir: Path = EVAL_DIR,
                          force: bool = False) -> str:
    """Rebuild names.json and target.json next to a mask.json you were given. The salt is NOT changed.

    Use this on a second machine: copy mask.json (privately) into the eval folder, then restore. It
    first checks that the salt reproduces mask.json's own ids for every drug in THIS snapshot, so a
    wrong snapshot, a wrong cutoff or a corrupted file is refused instead of silently giving other
    ids. The map may hold MORE drugs than the snapshot (the pool can shrink, as it did from 1885
    to 1146); masking depends only on the salt, so the extra entries are harmless.
    """
    eval_dir = Path(eval_dir)
    try:
        given = json.loads((eval_dir / "mask.json").read_text())
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{exc.filename} missing: copy the mask.json you were sent into "
                                f"{eval_dir} first (do NOT run init: it would create a different salt)") from exc
    expected = {masked_id(given["salt"], d): d for d in snap.drugs}
    if any(given["map"].get(mid) != drug for mid, drug in expected.items()):
        raise ValueError("mask.json does not match this snapshot: the salt, the cutoff or the "
                         "snapshot differs from the one it was made for. Nothing was written.")
    existing = [f for f in ("names.json", "target.json") if (eval_dir / f).exists()]
    if existing and not force:
        raise FileExistsError(f"{existing} already in {eval_dir}; pass --force to rebuild them")
    names, target = _names_and_target(snap, conn)
    _write_private(eval_dir / "names.json", {d: names.get(d) or d for d in snap.drugs})
    _write_private(eval_dir / "target.json", {"target_chembl_id": target})
    return fingerprint(given["salt"])


def other_masks(eval_dir: Path) -> list[Path]:
    """mask.json files at the other known locations (home folder, old in-repo folder)."""
    here = Path(eval_dir).resolve()
    return [p for p in (HOME_DIR / "mask.json", LEGACY_DIR / "mask.json")
            if p.exists() and p.parent.resolve() != here]


def main(argv: list[str] | None = None) -> None:
    import argparse

    from lab import chembl
    ap = argparse.ArgumentParser(description="Create or restore the eval-only masking files.")
    ap.add_argument("command", choices=["init", "restore"], nargs="?", default="init",
                    help="init: new salt (first time only). restore: rebuild names/target from a mask.json you were given")
    ap.add_argument("--force", action="store_true",
                    help="init: rotate the salt, renaming every drug. restore: overwrite names.json/target.json")
    args = ap.parse_args(argv)
    try:
        if args.command == "init" and (others := other_masks(EVAL_DIR)):
            raise FileExistsError(
                f"another mask.json already exists at {[str(p) for p in others]}. A second one means two "
                f"salts and different masked ids. Use that folder (set LAB_EVAL_DIR to it), or, if it is "
                f"a mistake, delete it first. To use a mask someone sent you, run `restore`, not `init`.")
        run = restore_from_snapshot if args.command == "restore" else init_from_snapshot
        if args.command == "init" and args.force and (EVAL_DIR / "mask.json").exists():
            print("rotating the salt: every masked id changes. The old mask.json is kept as "
                  f"mask.<fingerprint>.bak.json in {EVAL_DIR}; delete it only if no ledger row or shared copy needs it.")
        fp = run(snapshot_mod.load(), chembl.connect(), eval_dir=EVAL_DIR, force=args.force)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from None
    print(f"{args.command} done in {EVAL_DIR}  salt fingerprint {fp}  (the salt itself is never printed)")

if __name__ == "__main__":
    main()

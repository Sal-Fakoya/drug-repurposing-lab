"""Build the static dashboard: one self-contained HTML file, no network, no JavaScript.

    python dashboard/build.py [--mode toy|real] [--out dashboard/out/index.html]

Skeleton: safety banner, SYNTHETIC bar, provenance (from the verified snapshot manifest) and the
limitations. Results, ranking and the reasoning trail are added in later steps. Everything that
comes from a file is HTML-escaped: Europe PMC text will be untrusted. Only the salt FINGERPRINT is
ever shown; the salt and the eval-only files are never read for content.
"""
import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import lab  # noqa: E402
from lab import masking, snapshot  # noqa: E402

BANNER = "Agent-generated hypotheses. Not medical advice. Needs laboratory and clinical validation."
SYNTHETIC = "SYNTHETIC DATA: this is not a finding."
QUESTION = ("For patients whose idiopathic multicentric Castleman disease does not respond to IL-6 "
            "blockade, which approved drug should be tested next?")
OUT = ROOT / "dashboard" / "out" / "index.html"
LIMITATIONS = ROOT / "LIMITATIONS.md"

CSS = """
:root{--bg:#fafaf7;--fg:#1c1b19;--muted:#5d5a52;--line:#d9d6cc;--card:#fff;--warn:#7a1f1f;--warn-bg:#fbe9e7;
--note:#7a5200;--note-bg:#fff4d6}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;--muted:#a9a69c;--line:#3a3935;--card:#1f1f1c;
--warn:#ffb4a9;--warn-bg:#3b1a17;--note:#ffd98a;--note-bg:#33290f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.bars{position:sticky;top:0;z-index:2}
.bar{padding:.6rem 1rem;font-weight:600;text-align:center}
.banner{background:var(--note-bg);color:var(--note);border-bottom:2px solid var(--note)}
.synthetic{background:var(--warn-bg);color:var(--warn);border-bottom:2px solid var(--warn);letter-spacing:.04em}
main{max-width:56rem;margin:0 auto;padding:1.5rem 1rem 4rem}
h1{font-size:1.7rem;margin:.2rem 0}h2{font-size:1.15rem;margin:2.2rem 0 .6rem;padding-bottom:.3rem;border-bottom:1px solid var(--line)}
.q{color:var(--muted);margin:.2rem 0 1rem}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line)}
th,td{text-align:left;padding:.5rem .7rem;border-bottom:1px solid var(--line);vertical-align:top}
th{width:13rem;color:var(--muted);font-weight:600}td{overflow-wrap:anywhere}code{font-size:.9em}
.pending{background:var(--card);border:1px dashed var(--line);padding:.8rem 1rem;color:var(--muted)}
.todo{background:var(--warn-bg);color:var(--warn);padding:0 .35rem;border-radius:3px;font-size:.8em;margin-left:.4rem}
li{margin:.25rem 0}@media print{.bars{position:static}}
"""


def e(text) -> str:
    return html.escape(str(text), quote=True)


def provenance(mode: str, cutoff: int, snapshot_root: Path, eval_dir: Path | None) -> list[tuple[str, str]]:
    rows = [("Mode", mode), ("Cutoff", f"publications dated up to {cutoff - 1}-12-31 (exclusive year {cutoff})")]
    if mode == "toy":
        return rows + [("Data", "synthetic toy data (lab/toy_data.py); no snapshot")]
    snap = snapshot.load(cutoff, snapshot_root)           # verifies every hash; raises if missing or edited
    m = snap.manifest
    rows += [
        ("ChEMBL", f"{m['chembl']['release']} ({str(m['chembl']['creation_date'])[:10]})"),
        ("MSigDB", m["msigdb"]["version"]),
        ("Snapshot SHA-256", snap.sha256),
        ("Drugs in pool", str(m["counts"]["drugs"])),
        ("Analysis 1 (primary)", m["rules"]["curated"]),
        ("Analysis 2 (sensitivity)", m["rules"]["curated+activity"]),
        ("Gene sets", m["rules"]["gene_sets"]),
    ]
    if eval_dir is not None:
        rows.append(("Mask (salt fingerprint)", masking.load(eval_dir).fingerprint))
    return rows


def render_markdown(text: str) -> tuple[str, int]:
    """Minimal, escaping renderer for LIMITATIONS.md. Returns (html, number of TODO lines)."""
    out, todos, in_list = [], 0, False
    for line in text.splitlines():
        if in_list and not line.startswith("- "):
            out.append("</ul>")
            in_list = False
        if not line.strip() or line.startswith("# "):
            continue
        todo = "TODO" in line
        todos += todo
        tag = '<span class="todo">to be completed</span>' if todo else ""
        if line.startswith("## "):
            out.append(f"<h3>{e(line[3:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{e(line[2:])}{tag}</li>")
        else:
            out.append(f"<p>{e(line)}{tag}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out), todos


def render(mode: str, cutoff: int, prov: list[tuple[str, str]], limitations_html: str,
           synthetic: bool) -> str:
    bars = f'<div class="bar banner" role="note">{e(BANNER)}</div>'
    if synthetic:
        bars += f'<div class="bar synthetic" role="alert">{e(SYNTHETIC)}</div>'
    table = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in prov)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drug repurposing lab: replay dashboard</title><style>{CSS}</style></head>
<body><header class="bars">{bars}</header>
<main>
<h1>Drug repurposing lab</h1>
<p class="q">{e(QUESTION)}</p>
<h2>Results, ranking and reasoning trail</h2>
<div class="pending">Not available yet. These sections are added once real runs exist for both analyses.</div>
<h2>Provenance</h2>
<table>{table}</table>
<h2>Limitations</h2>
{limitations_html}
</main></body></html>
"""


def build(out: Path = OUT, mode: str | None = None, cutoff: int = lab.CUTOFF_YEAR,
          snapshot_root: Path = snapshot.SNAPSHOT_ROOT, limitations_path: Path = LIMITATIONS,
          eval_dir: Path | None = None) -> Path:
    mode = mode or lab.MODE
    if mode == "real" and eval_dir is None:
        eval_dir = masking.EVAL_DIR
    prov = provenance(mode, cutoff, snapshot_root, eval_dir if mode == "real" else None)
    limits, todos = render_markdown(Path(limitations_path).read_text(encoding="utf-8"))
    if todos:
        print(f"warning: {todos} TODO line(s) in {limitations_path.name} are shown on the dashboard",
              file=sys.stderr)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(mode, cutoff, prov, limits, synthetic=(mode == "toy")), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=["toy", "real"], default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    print(f"wrote {build(args.out, args.mode)}")

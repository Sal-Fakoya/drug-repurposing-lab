"""Build the static dashboard: one self-contained HTML file, no network, no JavaScript.

    python dashboard/build.py [--mode toy|real] [--out dashboard/out/index.html]

Skeleton: safety banner, SYNTHETIC bar, provenance (from the verified snapshot manifest) and the
limitations. The page-wide SYNTHETIC bar shows if the mode is toy OR any loaded ledger row is
synthetic (a row with no `synthetic` field counts as synthetic: unknown provenance is flagged), and
each synthetic row carries its own tag. Note `synthetic` comes from LAB_MODE: it flags the run mode,
not each source. Results, ranking and the reasoning trail are added in later steps. Everything that
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
SYNTHETIC_TAG = '<span class="tag">synthetic</span>'
OUT = ROOT / "dashboard" / "out" / "index.html"
LIMITATIONS = ROOT / "LIMITATIONS.md"

CSS = """
:root{--paper:#F4F1E8;--panel:#FBF9F2;--ink:#14181D;--muted:#5B6068;--soft:rgba(20,24,29,.16);
--grid:rgba(20,24,29,.045);--shadow:#14181D;--mark:#FFF3A8;--signal:#B3261E;
--serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
--sans:ui-sans-serif,system-ui,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--paper:#15171A;--panel:#1C1F23;--ink:#ECE9DF;--muted:#A8A69E;
--soft:rgba(236,233,223,.2);--grid:rgba(236,233,223,.05);--shadow:rgba(236,233,223,.28)}}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font:16px/1.6 var(--sans);background-color:var(--paper);
background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
background-size:32px 32px}
a:focus-visible{outline:3px solid var(--ink);outline-offset:2px}
.bars{position:sticky;top:0;z-index:5}
.bar{padding:.55rem 1rem;text-align:center;font-size:.95rem;font-weight:600;border-bottom:1px solid #14181D}
.banner{background:var(--mark);color:#14181D}
.synthetic{background:var(--signal);color:#fff;font-weight:700;letter-spacing:.02em}
.site,main{max-width:72rem;margin:0 auto;padding-left:1rem;padding-right:1rem}
.site{padding-top:1rem;padding-bottom:.4rem;display:flex;justify-content:space-between;align-items:center;gap:.8rem;flex-wrap:wrap}
.name{font:700 1.15rem var(--serif)}
.chips{display:flex;gap:.5rem;flex-wrap:wrap}
.chip{border:1px solid var(--ink);background:var(--panel);padding:.1rem .6rem;border-radius:2px;font-size:.88rem}
main{padding-bottom:5rem}
.hero{display:grid;gap:2rem;padding:1.6rem 0 2rem;border-bottom:1px solid var(--ink)}
h1{font:700 clamp(1.7rem,3.4vw,2.6rem)/1.14 var(--serif);letter-spacing:-.01em;margin:0 0 1.6rem;max-width:26em}
figure{margin:0}
.ruler{display:block;width:100%;max-width:40rem;height:auto}
figcaption{margin-top:.5rem;max-width:44em;color:var(--muted);font-size:.92rem}
.yr{fill:var(--ink);font:16px var(--sans)}
.cap{fill:var(--muted);font:16px var(--sans)}
.read{fill:var(--mark);stroke:#14181D;stroke-width:1}
.readtxt{fill:#14181D;font:600 16px var(--sans)}
.hide{fill:url(#hide);stroke:var(--ink);stroke-width:1}
.hatch{stroke:var(--muted);stroke-width:1.5}
.cut{stroke:var(--ink);stroke-width:3}
.axis{stroke:var(--ink);stroke-width:1}
.cutlab{fill:var(--ink);font:700 16px var(--sans)}
.run{background:var(--panel);border:1px solid var(--ink);border-radius:2px;padding:1rem 1.15rem;box-shadow:4px 4px 0 var(--shadow)}
.run h2{font:700 1.05rem var(--serif);margin:0 0 .5rem}
.run p{margin:.55rem 0 0;font-size:.95rem;max-width:36em}
.pills{display:flex;flex-wrap:wrap;gap:.5rem;padding:1.2rem 0 .4rem}
.pills a{border:1px solid var(--ink);background:var(--panel);color:var(--ink);padding:.3rem .85rem;border-radius:2px;text-decoration:none;font-size:.95rem}
.pills a:hover{background:var(--mark);color:#14181D}
.sec{padding:1.4rem 0 1rem}
.sec h2{font:700 1.5rem/1.2 var(--serif);margin:0}
.sec h3{font:700 1.05rem var(--serif);margin:1.4rem 0 .3rem}
.lede{margin:.25rem 0 1rem;max-width:60ch;color:var(--muted)}
.empty{border:1px dashed var(--ink);background:var(--panel);border-radius:2px;padding:1.1rem 1.2rem}
.empty strong{display:block;font:700 1.05rem var(--serif)}
.empty p{margin:.25rem 0 0;max-width:56ch;color:var(--muted)}
.pair{display:grid;gap:1rem}
.panel{background:var(--panel);border:1px solid var(--ink);border-radius:2px;padding:1rem 1.1rem}
.panel h3{margin:0}
.sub{margin:.1rem 0 .8rem;color:var(--muted);font-size:.92rem}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--ink)}
th,td{text-align:left;padding:.5rem .7rem;border-bottom:1px solid var(--soft);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.9rem}
code,.mono{font-family:var(--mono);font-size:.88rem}
.facts{margin:0;background:var(--panel);border:1px solid var(--ink)}
.facts div{display:grid;grid-template-columns:12rem minmax(0,1fr);gap:1rem;padding:.6rem .85rem;border-bottom:1px solid var(--soft)}
.facts div:last-child{border-bottom:0}
dt{color:var(--muted);font-weight:600;font-size:.92rem}
dd{margin:0;overflow-wrap:anywhere}
.tag{background:var(--signal);color:#fff;padding:.05rem .4rem;border-radius:2px;font-size:.8rem;font-weight:600}
.todo{background:var(--mark);color:#14181D;border:1px solid #14181D;padding:0 .4rem;border-radius:2px;font-size:.8rem;margin-left:.4rem}
li{margin:.3rem 0;max-width:68ch}
@media (min-width:48rem){.pair{grid-template-columns:1fr 1fr}}
@media (min-width:58rem){.hero{grid-template-columns:minmax(0,1fr) 19rem;align-items:start}.run{position:sticky;top:6.5rem}}
@media (max-width:40rem){.facts div{grid-template-columns:1fr;gap:.1rem}}
@media print{.bars,.run{position:static}.run{box-shadow:none}body{background:#fff;color:#000}}
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


def is_synthetic(row: dict) -> bool:
    return bool(row.get("synthetic", True))     # fail safe: a row that does not say is flagged


def check_rows(rows: list[dict]) -> None:
    for r in rows:
        if not isinstance(r, dict) or "id" not in r or "kind" not in r:
            raise ValueError(f"ledger row needs an id and a kind: {str(r)[:80]!r}")


def render_rows(rows: list[dict]) -> str:
    """Envelope fields only (never the payload), each synthetic row tagged."""
    body = "".join(
        f"<tr><td><code>{e(r['id'])}</code></td><td>{e(r['kind'])}</td><td>{e(r.get('agent') or '')}</td>"
        f"<td>{SYNTHETIC_TAG if is_synthetic(r) else ''}</td></tr>" for r in rows)
    return ("<h3>Ledger rows loaded</h3><table><tr><th>id</th><th>kind</th><th>agent</th><th></th></tr>"
            f"{body}</table>")


def render_ruler(cutoff: int) -> str:
    """Figure 1: a year scale, the span the lab can read highlighted, later years hatched.

    Built from the cutoff, so it moves if the cutoff changes. Inline SVG, no script, no network.
    """
    first, last = cutoff - 14, cutoff + 2                  # years shown: first .. last-1
    pad, width = 8, 520
    per = (width - 2 * pad) / (last - first)
    x = lambda year: round(pad + (year - first) * per, 1)  # noqa: E731
    cut = x(cutoff)
    ticks = "".join(f'<line class="axis" x1="{x(y)}" y1="62" x2="{x(y)}" y2="68"/>' for y in range(first, last + 1))
    labels = "".join(f'<text class="yr" x="{x(y)}" y="88" text-anchor="middle">{y}</text>'
                     for y in range(first, last + 1) if y % 5 == 0 and y != cutoff)
    title = (f"Timeline: the lab can read publications up to 31 December {cutoff - 1}. "
             "Later publications are hidden from it.")
    return (
        f'<figure><svg class="ruler" viewBox="0 0 {width} 118" role="img" aria-labelledby="rt">'
        f'<title id="rt">{e(title)}</title>'
        '<defs><pattern id="hide" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<line class="hatch" x1="0" y1="0" x2="0" y2="6"/></pattern></defs>'
        f'<rect class="read" x="{pad}" y="34" width="{round(cut - pad, 1)}" height="28"/>'
        f'<rect class="hide" x="{cut}" y="34" width="{round(width - pad - cut, 1)}" height="28"/>'
        f'<line class="axis" x1="{pad}" y1="62" x2="{width - pad}" y2="62"/>{ticks}'
        f'<line class="cut" x1="{cut}" y1="22" x2="{cut}" y2="74"/>'
        f'<text class="cutlab" x="{round(cut - 6, 1)}" y="17" text-anchor="end">31 Dec {cutoff - 1}</text>'
        f'<text class="readtxt" x="{pad + 10}" y="54">The lab can read this</text>'
        f'{labels}'
        f'<text class="yr" x="{cut}" y="88" text-anchor="middle" font-weight="700">{cutoff}</text>'
        f'<text class="cap" x="{width - pad}" y="110" text-anchor="end">Not available to the lab</text></svg>'
        f"<figcaption>Figure 1. Evidence stops at 31 December {e(cutoff - 1)}. "
        "Everything published later is hidden from the lab.</figcaption></figure>")


def render_facts(prov: list[tuple[str, str]]) -> str:
    def cell(key: str, value: str) -> str:
        mono = ' class="mono"' if ("SHA-256" in key or "fingerprint" in key) else ""
        return f"<div><dt>{e(key)}</dt><dd{mono}>{e(value)}</dd></div>"
    return '<dl class="facts">' + "".join(cell(k, v) for k, v in prov) + "</dl>"


def render(mode: str, cutoff: int, prov: list[tuple[str, str]], limitations_html: str,
           synthetic: bool, rows: list[dict] | None = None) -> str:
    bars = f'<div class="bar banner" role="note">{e(BANNER)}</div>'
    if synthetic:
        bars += f'<div class="bar synthetic" role="alert">{e(SYNTHETIC)}</div>'
    saw = (render_rows(rows) if rows else
           '<div class="empty"><strong>No run loaded</strong>'
           "<p>Build the dashboard with a run's ledger rows to see its hypotheses, experiments and "
           "verdicts here.</p></div>")
    none = '<div class="empty"><strong>No run loaded</strong><p>Nothing to score for this analysis yet.</p></div>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drug repurposing lab: replay dashboard</title><style>{CSS}</style></head>
<body><header class="bars">{bars}</header>
<div class="site"><span class="name">Drug repurposing lab</span>
<span class="chips"><span class="chip">Cutoff {e(cutoff)}</span><span class="chip">{"Toy mode" if mode == "toy" else "Real data"}</span></span></div>
<main>
<section class="hero">
<div><h1>{e(QUESTION)}</h1>{render_ruler(cutoff)}</div>
<aside class="run" aria-label="How to read this page"><h2>How to read this page</h2>
<p>The lab never saw drug names. The first view shows what it saw.</p>
<p>The second view scores the result afterwards. It is the only place the answer is shown.</p>
<p>Everything here is a hypothesis for laboratory validation, not advice.</p></aside>
</section>
<nav class="pills" aria-label="Sections"><a href="#saw">What the lab saw</a><a href="#scored">How it scored afterwards</a><a href="#provenance">Provenance</a><a href="#limits">Limitations</a></nav>
<section class="sec" id="saw"><h2>What the lab saw</h2>
<p class="lede">Hypotheses, experiments and verdicts, with drug names masked.</p>{saw}</section>
<section class="sec" id="scored"><h2>How it scored afterwards</h2>
<p class="lede">Both analyses are reported, whatever they show. Real names and the target highlight appear only here.</p>
<div class="pair">
<div class="panel"><h3>Analysis 1</h3><p class="sub">Curated drug-target links</p>{none}</div>
<div class="panel"><h3>Analysis 2</h3><p class="sub">Curated links plus recorded activity</p>{none}</div></div></section>
<section class="sec" id="provenance"><h2>Provenance</h2>{render_facts(prov)}</section>
<section class="sec" id="limits"><h2>Limitations</h2>{limitations_html}</section>
</main></body></html>
"""


def build(out: Path = OUT, mode: str | None = None, cutoff: int = lab.CUTOFF_YEAR,
          snapshot_root: Path = snapshot.SNAPSHOT_ROOT, limitations_path: Path = LIMITATIONS,
          eval_dir: Path | None = None, rows: list[dict] | None = None) -> Path:
    mode = mode or lab.MODE
    if mode == "real" and eval_dir is None:
        eval_dir = masking.EVAL_DIR
    rows = rows or []
    check_rows(rows)
    prov = provenance(mode, cutoff, snapshot_root, eval_dir if mode == "real" else None)
    if rows:
        prov.append(("Ledger rows", f"{len(rows)} loaded, {sum(map(is_synthetic, rows))} synthetic"))
    limits, todos = render_markdown(Path(limitations_path).read_text(encoding="utf-8"))
    if todos:
        print(f"warning: {todos} TODO line(s) in {limitations_path.name} are shown on the dashboard",
              file=sys.stderr)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(mode, cutoff, prov, limits, synthetic=(mode == "toy" or any(map(is_synthetic, rows))), rows=rows),
                   encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=["toy", "real"], default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    print(f"wrote {build(args.out, args.mode)}")

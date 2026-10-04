"""Build the single-file demo page from a finished run: python dashboard/make_index.py LEDGER_DIR --out index.html

LEDGER_DIR holds ledger.jsonl (masked) and eval_only.jsonl (target ranks). Shows hypotheses, experiments and
the target's post-hoc rank. No gene sets, no evidence text, no drug names.
"""
import argparse
import importlib.util
import json
import statistics
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("dashboard_build", Path(__file__).with_name("build.py"))
b = importlib.util.module_from_spec(_spec)
sys.modules["dashboard_build"] = b
_spec.loader.exec_module(b)
e = b.e


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def trail_html(rows):
    hyps = {r["id"]: dict(r["payload"]) for r in rows if r["kind"] == "hypothesis"}
    for r in rows:  # last confidence update wins
        if r["kind"] == "hypothesis_update" and r["payload"]["hyp_id"] in hyps:
            hyps[r["payload"]["hyp_id"]]["confidence"] = r["payload"]["confidence"]
    verdicts = {}
    for r in rows:
        if r["kind"] == "verdict":
            verdicts.setdefault(r["payload"]["hyp_id"], []).append(
                f"{r['payload']['verdict']} (z={float(r['payload']['z']):.1f})")
    body = "".join(
        f"<tr><td><code>{e(i)}</code></td><td>{e(h['claim'])}</td><td>{e(h.get('confidence'))}</td>"
        f"<td>{e(', '.join(verdicts.get(i, [])) or 'not tested')}</td></tr>" for i, h in hyps.items())
    return ("<h3>Hypotheses the lab proposed</h3><p class=\"sub\">Agent-generated. Confidence is a model "
            "estimate, not a probability.</p><table><tr><th>id</th><th>claim</th><th>confidence</th>"
            f"<th>verdicts</th></tr>{body}</table>")


def scored_html(rows, eval_rows, definition):
    ranks = {r["res_id"]: r["target_drug_rank"] for r in eval_rows}
    specs = {r["id"]: r["payload"] for r in rows if r["kind"] == "experiment_spec"}
    lines, vals = "", []
    for r in rows:
        if r["kind"] != "result" or r["id"] not in ranks:
            continue
        s = specs.get(r["payload"]["exp_id"], {})
        n = len(r["payload"]["ranked_drugs"])
        control = s.get("hyp_id") == "negative_control"
        if not control:
            vals.append(ranks[r["id"]])
        lines += (f"<tr><td><code>{e(r['id'])}</code></td><td>{e(s.get('hyp_id'))}</td><td>{e(s.get('method'))}</td>"
                  f"<td>{ranks[r['id']]:g} of {n}</td><td>{'negative control' if control else ''}</td></tr>")
    top = (f"<p>Target mid-rank, best <strong>{min(vals):g}</strong>, median <strong>{statistics.median(vals):g}</strong> "
           "across hypothesis experiments (rank 1 is best; ties share a mid-rank).</p>") if vals else ""
    one = (f"{top}<table><tr><th>result</th><th>hypothesis</th><th>method</th><th>target mid-rank</th><th></th></tr>"
           f"{lines}</table><p class=\"sub\">Drug names are not shown on this page. "
           f"Link definition: {e(definition)}. One run, one seed, not replicated.</p>")
    other = '<div class="empty"><strong>Not run in this build</strong><p>Reported as not run, not omitted.</p></div>'
    return (one, other) if definition == "curated" else (other, one)


def headline_html(rows, eval_rows):
    """Dot plot: where the target landed in each result, 1 (best) at the left, the pool's middle in yellow."""
    ranks = {r["res_id"]: r["target_drug_rank"] for r in eval_rows}
    specs = {r["id"]: r["payload"] for r in rows if r["kind"] == "experiment_spec"}
    res = [r for r in rows if r["kind"] == "result" and r["id"] in ranks]
    if not res:
        return ""
    n = len(res[0]["payload"]["ranked_drugs"])
    x0, x1, step = 70, 620, 22
    px = lambda v: x0 + (v - 1) / (n - 1) * (x1 - x0)  # noqa: E731
    h = 40 + step * len(res)
    best = min(ranks[r["id"]] for r in res)
    middle = sum(0.4 * n <= ranks[r["id"]] <= 0.6 * n for r in res)
    g = [f'<rect x="{px(0.4 * n):.0f}" y="24" width="{px(0.6 * n) - px(0.4 * n):.0f}" height="{step * len(res)}" fill="var(--mark)"/>']
    for i, r in enumerate(res):
        y = 24 + step * i + step / 2
        v = ranks[r["id"]]
        ctrl = specs.get(r["payload"]["exp_id"], {}).get("hyp_id") == "negative_control"
        fill = "var(--paper)" if ctrl else ("var(--signal)" if v == best else "var(--ink)")
        g.append(f'<text class="m" x="0" y="{y + 5:.0f}">{e(r["id"])}</text>'
                 f'<line x1="{x0}" x2="{x1}" y1="{y:.0f}" y2="{y:.0f}" stroke="var(--soft)"/>'
                 f'<circle cx="{px(v):.0f}" cy="{y:.0f}" r="6" fill="{fill}" stroke="var(--ink)" stroke-width="1.5"/>')
    g.append(f'<text class="m" x="{x0}" y="14">1 (best)</text><text class="m" x="{x1}" y="14" text-anchor="end">{n} (worst)</text>'
             f'<text class="m" x="{(x0 + x1) / 2:.0f}" y="14" text-anchor="middle">pool middle</text>')
    svg = (f'<svg viewBox="0 0 640 {h}" role="img" aria-label="Target rank per result, out of {n} drugs">'
           + "".join(g) + "</svg>")
    return (f'<figure class="headline"><h3>Where the target landed</h3>'
            f'<p class="sub">{middle} of {len(res)} results left the target near the middle of {n} drugs, '
            f'in the tie group. Best: rank {best:g}. Hollow dot: negative control.</p>{svg}</figure>')


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("index.html"))
    ap.add_argument("--definition", choices=["curated", "curated+activity"], default="curated")
    ap.add_argument("--note", default="", help="plain-text run description shown above the hypotheses")
    ap.add_argument("--snapshot-root", type=Path, default=b.snapshot.SNAPSHOT_ROOT)
    ap.add_argument("--eval-dir", type=Path, default=None)
    a = ap.parse_args()
    rows = _jsonl(a.ledger_dir / "ledger.jsonl")
    ev = _jsonl(a.ledger_dir / "eval_only.jsonl")
    note = '<p class="lede">' + e(a.note) + "</p>" if a.note else ""
    out = b.build(a.out, "real", snapshot_root=a.snapshot_root, eval_dir=a.eval_dir, rows=rows,
                  trail=note + trail_html(rows), scored=scored_html(rows, ev, a.definition), headline=headline_html(rows, ev))
    print(f"wrote {out}")

"""Build the single-file demo page from a finished run: python dashboard/make_index.py LEDGER_DIR --out index.html

LEDGER_DIR holds ledger.jsonl (masked) and eval_only.jsonl (target ranks). Shows hypotheses, experiments and
the target's post-hoc rank. No gene sets, no evidence text, no drug names (the approval gate has not run).
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
           f"{lines}</table><p class=\"sub\">Drug names are withheld: the human approval gate has not been passed. "
           f"Link definition: {e(definition)}. One run, one seed, not replicated.</p>")
    other = '<div class="empty"><strong>Not run in this build</strong><p>Reported as not run, not omitted.</p></div>'
    return (one, other) if definition == "curated" else (other, one)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("index.html"))
    ap.add_argument("--definition", choices=["curated", "curated+activity"], default="curated")
    ap.add_argument("--snapshot-root", type=Path, default=b.snapshot.SNAPSHOT_ROOT)
    ap.add_argument("--eval-dir", type=Path, default=None)
    a = ap.parse_args()
    rows = _jsonl(a.ledger_dir / "ledger.jsonl")
    ev = _jsonl(a.ledger_dir / "eval_only.jsonl")
    print(f"wrote {b.build(a.out, 'real', snapshot_root=a.snapshot_root, eval_dir=a.eval_dir, rows=rows, trail=trail_html(rows), scored=scored_html(rows, ev, a.definition))}")

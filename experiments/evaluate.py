"""Evaluate the lab against its baselines on the same budget and data.

    python experiments/evaluate.py                     # 100 seeds, all arms, current LAB_MODE
    python experiments/evaluate.py --seeds 20 --agent-ledger path/to/runtime_dir

Writes experiments/out/<mode>/: runs/ (one ledger and eval-only file per run), results.csv,
results.md and target_rank_vs_experiments.png. Metrics come only from the eval-only files.
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python experiments/evaluate.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lab  # noqa: E402
from experiments import harness, metrics  # noqa: E402

DEFAULT_ARMS = ["agent", "random", "no_reopen", harness.COOCCURRENCE]


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=100, help="seeds per arm (default 100)")
    parser.add_argument("--arms", nargs="+", default=DEFAULT_ARMS,
                        choices=[*harness.LAB_ARMS, harness.COOCCURRENCE])
    parser.add_argument("--agent-ledger", nargs="*", default=[], type=Path,
                        help="runtime dirs of real Omnigent runs to include as agent_omnigent")
    parser.add_argument("--out", type=Path, default=None,
                        help="output dir (default experiments/out/<LAB_MODE>)")
    args = parser.parse_args(argv)
    out = args.out or Path(__file__).resolve().parent / "out" / lab.MODE
    config = harness.load_config()
    harness.run_all(out, list(range(args.seeds)), args.arms, config, args.agent_ledger)
    rows = metrics.load_eval_rows(out)
    summary = metrics.summarize(rows)
    csv_path, md_path = metrics.write_table(summary, out)
    png = metrics.plot(rows, out)
    print(md_path.read_text())
    print(f"wrote {csv_path}\nwrote {md_path}\nwrote {png}")
    return {"summary": summary, "csv": csv_path, "md": md_path, "png": png}


if __name__ == "__main__":
    main()

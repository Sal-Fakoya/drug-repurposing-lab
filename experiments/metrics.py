"""Metrics, read only from the eval-only files the harness wrote. No ledger access.

Per run: experiments until the target enters the top 10 (first step with mid-rank <= 10), and
the target's final mid-rank. Per arm: their distributions over seeds.
"""
import csv
import json
import math
from pathlib import Path

import numpy as np

TOP = 10
LABELS = {
    "agent": "Agent pipeline (Thompson planner + reopen)",
    "random": "Random arm order (+ reopen)",
    "no_reopen": "Agent pipeline without reopen",
    "cooccurrence": "Literature co-occurrence ranking",
    "agent_omnigent": "Agent (Omnigent runs)",
}
ORDER = ["agent", "agent_omnigent", "random", "no_reopen", "cooccurrence"]


def load_eval_rows(out_dir: Path) -> list[dict]:
    """Every harness row (rows with a step) from out_dir/runs/**/eval_only.jsonl."""
    rows = []
    for path in sorted((Path(out_dir) / "runs").rglob("eval_only.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                if "step" in row:
                    rows.append(row)
    return rows


def trajectories(rows: list[dict]) -> dict[str, dict[int, dict]]:
    """{arm: {seed: {"steps": [...], "ranks": [...], "constant": bool}}}, sorted by step."""
    out: dict[str, dict[int, dict]] = {}
    for row in rows:
        run = out.setdefault(row["arm"], {}).setdefault(
            row["seed"], {"points": [], "constant": bool(row.get("constant"))})
        run["points"].append((row["step"], row["target_drug_rank"]))
    for runs in out.values():
        for run in runs.values():
            run["points"].sort()
            run["steps"] = [s for s, _ in run["points"]]
            run["ranks"] = [r for _, r in run["points"]]
            del run["points"]
    return out


def experiments_to_top(run: dict, top: int = TOP) -> int | None:
    """First experiment count at which the target's mid-rank is within the top; None if never."""
    return next((s for s, r in zip(run["steps"], run["ranks"]) if r <= top), None)


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return (math.nan, math.nan, math.nan)
    q1, med, q3 = np.percentile(values, [25, 50, 75])
    return (float(q1), float(med), float(q3))


def summarize(rows: list[dict], top: int = TOP) -> list[dict]:
    """One summary row per arm: distributions over seeds."""
    table = []
    traj = trajectories(rows)
    for arm in sorted(traj, key=lambda a: (ORDER.index(a) if a in ORDER else 99, a)):
        runs = list(traj[arm].values())
        reached = [e for e in (experiments_to_top(r, top) for r in runs) if e is not None]
        finals = [r["ranks"][-1] for r in runs]
        experiments = [r["steps"][-1] for r in runs]
        e_q1, e_med, e_q3 = _quartiles(reached)
        f_q1, f_med, f_q3 = _quartiles(finals)
        table.append({
            "arm": arm, "label": LABELS.get(arm, arm), "runs": len(runs),
            "experiments_median": float(np.median(experiments)),
            f"reached_top{top}": len(reached) / len(runs),
            f"exp_to_top{top}_median": e_med, f"exp_to_top{top}_q1": e_q1,
            f"exp_to_top{top}_q3": e_q3,
            "final_midrank_median": f_med, "final_midrank_q1": f_q1, "final_midrank_q3": f_q3,
            "final_midrank_mean": float(np.mean(finals)),
            "final_midrank_best": float(min(finals)), "final_midrank_worst": float(max(finals)),
        })
    return table


def _fmt(x: float) -> str:
    return "-" if isinstance(x, float) and math.isnan(x) else f"{x:g}"


def write_table(summary: list[dict], out_dir: Path, top: int = TOP) -> tuple[Path, Path]:
    """results.csv (every column) and results.md (readable table)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path, md_path = out_dir / "results.csv", out_dir / "results.md"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    lines = [
        f"| Arm | Runs | Experiments (median) | Reached top {top} | "
        f"Experiments to top {top}, median [IQR] | Final mid-rank, median [IQR] | "
        f"Final mid-rank, best to worst |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        lines.append(
            f"| {s['label']} | {s['runs']} | {_fmt(s['experiments_median'])} | "
            f"{s[f'reached_top{top}']:.0%} | "
            f"{_fmt(s[f'exp_to_top{top}_median'])} [{_fmt(s[f'exp_to_top{top}_q1'])}, "
            f"{_fmt(s[f'exp_to_top{top}_q3'])}] | "
            f"{_fmt(s['final_midrank_median'])} [{_fmt(s['final_midrank_q1'])}, "
            f"{_fmt(s['final_midrank_q3'])}] | "
            f"{_fmt(s['final_midrank_best'])} to {_fmt(s['final_midrank_worst'])} |")
    lines.append("")
    lines.append(f"Mid-rank: the mean of the first and last rank of the target's tie group "
                 f"(lower is better). Experiments to top {top} is over the runs that reached it.")
    md_path.write_text("\n".join(lines) + "\n")
    return csv_path, md_path


def rank_matrix(runs: dict[int, dict], max_step: int) -> np.ndarray:
    """Runs x steps; after a run ends its final rank carries forward (that is what it publishes)."""
    matrix = np.empty((len(runs), max_step + 1))
    for i, run in enumerate(runs.values()):
        by_step = dict(zip(run["steps"], run["ranks"]))
        current = run["ranks"][0]
        for step in range(max_step + 1):
            current = by_step.get(step, current)
            matrix[i, step] = current
    return matrix


def plot(rows: list[dict], out_dir: Path, top: int = TOP) -> Path:
    """Target mid-rank versus experiment count: median and IQR band per arm."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    traj = trajectories(rows)
    max_step = max((r["steps"][-1] for runs in traj.values() for r in runs.values()), default=0)
    max_step = max(max_step, 1)
    fig, ax = plt.subplots(figsize=(8, 6))
    steps = np.arange(max_step + 1)
    for arm in sorted(traj, key=lambda a: (ORDER.index(a) if a in ORDER else 99, a)):
        m = rank_matrix(traj[arm], max_step)
        q1, med, q3 = np.percentile(m, [25, 50, 75], axis=0)
        label = f"{LABELS.get(arm, arm)} (n={m.shape[0]})"
        style = "--" if all(r["constant"] for r in traj[arm].values()) else "-"
        line, = ax.plot(steps, med, style, drawstyle="steps-post", label=label, linewidth=2)
        ax.fill_between(steps, q1, q3, step="post", alpha=0.15, color=line.get_color())
    ax.axhline(top, color="grey", linewidth=1, linestyle=":")
    ax.text(0, top, f" top {top}", va="bottom", color="grey", fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Experiments run")
    ax.set_ylabel("Target mid-rank (lower is better)")
    ax.set_title("Target rank versus experiment count (median, IQR band over seeds)")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2,
              frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = Path(out_dir) / "target_rank_vs_experiments.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path

"""Paired comparison of models over the same tasks.

The leaderboard's first version reported independent binomial intervals,
which was the wrong test. Every model answered the same 450 tasks, so task
difficulty is a *shared* source of variance; treating the models as
independent samples charges each of them for it separately and makes real
differences look like noise.

This bootstraps over tasks instead. On each resample every model is scored
on the same drawn tasks, so difficulty cancels in the difference and only
genuine disagreement carries weight. It also reports, for each pair, how
many tasks the two models actually disagreed on -- the quantity that
determines whether a comparison is resolvable at all.

No new data, no API calls: reads results/<run>/per_task/.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

ITERATIONS = 10000
SEED = 20260812  # fixed so the published intervals are reproducible


def load(run: str, metric: str):
    d = config.RESULTS_DIR / run / "per_task"
    models, data = [], {}
    for f in sorted(d.glob("*.json")):
        models.append(f.stem)
        data[f.stem] = {k: v[metric] for k, v in json.loads(f.read_text()).items()}
    # only tasks every model attempted, so comparisons are like-for-like
    common = set.intersection(*(set(v) for v in data.values()))
    return models, data, sorted(common)


def bootstrap(models, data, tasks, iterations=ITERATIONS):
    rng = random.Random(SEED)
    n = len(tasks)
    point = {m: sum(data[m][t] for t in tasks) / n for m in models}
    draws = {m: [] for m in models}
    diffs = {(a, b): [] for a in models for b in models if a < b}
    for _ in range(iterations):
        sample = [tasks[rng.randrange(n)] for _ in range(n)]
        means = {m: sum(data[m][t] for t in sample) / n for m in models}
        for m in models:
            draws[m].append(means[m])
        for (a, b) in diffs:
            diffs[(a, b)].append(means[a] - means[b])
    return point, draws, diffs


def pct(xs, p):
    s = sorted(xs)
    return s[max(0, min(len(s) - 1, int(p * len(s))))]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--metric", default="usable", choices=["usable", "pass", "vulnerable"])
    args = ap.parse_args()

    models, data, tasks = load(args.run, args.metric)
    point, draws, diffs = bootstrap(models, data, tasks)
    order = sorted(models, key=lambda m: -point[m])

    print(f"metric: {args.metric}@3   tasks common to all models: {len(tasks)}   "
          f"bootstrap: {ITERATIONS} resamples\n")
    print(f"{'model':26s} {'score':>7s}  {'95% CI (paired bootstrap)':>26s}")
    print("-" * 64)
    for m in order:
        lo, hi = pct(draws[m], 0.025), pct(draws[m], 0.975)
        print(f"{m:26s} {point[m]:6.1%}  [{lo:6.1%}, {hi:6.1%}]")

    print(f"\nPairwise: is the difference distinguishable from zero?\n")
    print(f"{'pair':52s} {'diff':>7s} {'95% CI':>18s} {'disagree':>9s}  verdict")
    print("-" * 100)
    sig = 0
    total = 0
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            total += 1
            key = (a, b) if a < b else (b, a)
            sign = 1 if key == (a, b) else -1
            ds = [sign * x for x in diffs[key]]
            lo, hi = pct(ds, 0.025), pct(ds, 0.975)
            disagree = sum(1 for t in tasks if data[a][t] != data[b][t])
            resolved = lo > 0
            sig += resolved
            if resolved or b == order[i + 1]:
                print(f"{a + ' vs ' + b:52s} {point[a]-point[b]:+6.1%} "
                      f"[{lo:+6.1%},{hi:+6.1%}] {disagree:9d}  "
                      f"{'DISTINGUISHABLE' if resolved else 'not resolved'}")
    print(f"\n{sig} of {total} pairwise comparisons are resolved at 95%.")

    # how much of the corpus discriminates at all
    all_same = sum(1 for t in tasks if len({data[m][t] for m in models}) == 1)
    print(f"{all_same}/{len(tasks)} tasks ({all_same/len(tasks):.0%}) give every model the same "
          f"outcome and cannot separate anything.")


if __name__ == "__main__":
    main()

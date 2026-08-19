"""Is a model actually safer than the reference set, or does it only look it?

The human-baseline table pools 4,941 model patterns against 450 human
references and puts an independent binomial interval on each row. That is the
wrong estimator twice over. The 4,941 are eleven models answering the same
450 tasks, so task difficulty is a shared random effect and the pooled
interval is too narrow. And each model is compared against the reference set
on *the same tasks*, so the comparison is paired and an unpaired interval
throws the pairing away -- which is the criticism this paper makes of the
literature in its own section on inference.

McNemar's test is the paired procedure for this design: of the tasks where
the model and the reference disagree on vulnerability, how lopsided is the
disagreement? Everything the two have in common cancels, which is most of the
corpus. We use the exact binomial form rather than the chi-square
approximation, because the discordant counts here are small enough (30-60 per
model) for the approximation to matter.

One pattern per task per model, matching the human-baseline convention: the
reference authors wrote one answer each.

No API calls. Reads committed predictions. Writes results/<run>/mcnemar_reference.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

# Screening a corpus means compiling tens of thousands of patterns people
# actually wrote, and CPython warns about constructs that are legal today and
# may not stay so -- `[[a-z]]`, `[a-z--0]`. The warning is about the pattern,
# not about us, and one per pattern buries the output. The patterns are
# screened as written either way.
warnings.filterwarnings("ignore", category=FutureWarning)

from regexbench.datasets import load_regexeval  # noqa: E402
from regexbench.safety import screen  # noqa: E402

WORKERS = 4


def is_vulnerable(pattern):
    try:
        return screen(pattern, empirical=True).risk.name != "SAFE"
    except Exception:
        return None


def binom_two_sided(b: int, c: int) -> float:
    """Exact two-sided binomial p on the discordant pairs, under p = 1/2.

    The two-sided value is twice the smaller tail, clipped at 1 -- the
    standard convention for the exact McNemar test, and the conservative one
    when the discordant total is odd.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def first_sample_per_task(model: str, run: str) -> dict[str, str]:
    out: dict[str, str] = {}
    rows = [json.loads(x) for x in
            (config.PREDICTIONS_DIR / run / f"{model}.jsonl").read_text().splitlines()
            if x.strip()]
    for r in sorted(rows, key=lambda r: (r["task_name"], r.get("sample", 0))):
        if r["task_name"].startswith("control/") or r["status"] != "ok" or not r.get("pattern"):
            continue
        out.setdefault(r["task_name"], normalize_pattern(r["pattern"])[0])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    args = ap.parse_args()

    by_name = {t.name: t for t in load_regexeval(str(config.require_dataset()))}
    models = sorted(p.stem for p in (config.PREDICTIONS_DIR / args.run).glob("*.jsonl"))
    samples = {m: first_sample_per_task(m, args.run) for m in models}
    tasks = sorted(set().union(*(set(v) for v in samples.values())))

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        gold = dict(zip(tasks, pool.map(is_vulnerable,
                                        [by_name[t].reference for t in tasks], chunksize=16)))

    out = {"run": args.run, "models": {}}
    print(f"{'model':26s} {'n':>5s} {'model%':>7s} {'gold%':>7s} "
          f"{'safer':>6s} {'worse':>6s} {'p (exact)':>10s}")
    for m in models:
        names = sorted(samples[m])
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            verdicts = list(pool.map(is_vulnerable, [samples[m][t] for t in names], chunksize=16))
        paired = [(gold[t], v) for t, v in zip(names, verdicts)
                  if gold[t] is not None and v is not None]
        n = len(paired)
        # b: reference vulnerable, model safe -- the model is better here.
        b = sum(1 for g, v in paired if g and not v)
        c = sum(1 for g, v in paired if v and not g)
        p = binom_two_sided(b, c)
        row = {"n": n, "model_vulnerable": sum(1 for _, v in paired if v),
               "gold_vulnerable": sum(1 for g, _ in paired if g),
               "model_safer_on": b, "model_worse_on": c, "discordant": b + c,
               "p_exact_two_sided": round(p, 4)}
        row["model_pct"] = round(100 * row["model_vulnerable"] / n, 1)
        row["gold_pct"] = round(100 * row["gold_vulnerable"] / n, 1)
        out["models"][m] = row
        print(f"{m:26s} {n:5d} {row['model_pct']:6.1f}% {row['gold_pct']:6.1f}% "
              f"{b:6d} {c:6d} {p:10.4f}", flush=True)

    resolved = [m for m, r in out["models"].items() if r["p_exact_two_sided"] < 0.05]
    out["resolved_at_95"] = sorted(resolved)
    out["models_tested"] = len(models)
    print(f"\n{len(resolved)} of {len(models)} models are distinguishable from the "
          f"reference set at 95%: {', '.join(sorted(resolved)) or 'none'}")

    path = config.RESULTS_DIR / args.run / "mcnemar_reference.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())

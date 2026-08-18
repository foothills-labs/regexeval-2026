"""Sample cases where a model passed every test but disagreed with the gold.

These are the cases `dfa-eq` and `usable` score against the model. Some of
them are the model being wrong. Some are the *reference* being wrong -- the
ISBN gold is `^\\d{9}[\\d|X]$`, a character class holding a literal pipe,
where the prompt plainly means "a digit or X".

Until that rate is measured, every score carries an unbounded correction.
This draws a reproducible random sample for a human to adjudicate, with the
prompt, both patterns and the witness string that separates them.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

from regexbench import Semantics, equivalent, evaluate  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402

SEED = 20260812


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--models", default="claude-opus-5,kimi-k3,gpt-5.6-sol")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    by_name = {t.name: t for t in load_regexeval(str(config.require_dataset()))}
    rng = random.Random(SEED)

    pool = []
    for m in [x.strip() for x in args.models.split(",")]:
        path = config.PREDICTIONS_DIR / args.run / f"{m}.jsonl"
        seen = set()
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["task_name"].startswith("control/") or r["status"] != "ok" or not r.get("pattern"):
                continue
            if r["task_name"] in seen:
                continue
            seen.add(r["task_name"])
            pool.append((m, r["task_name"], normalize_pattern(r["pattern"])[0]))

    rng.shuffle(pool)
    out = []
    for model, task_name, pat in pool:
        if len(out) >= args.n:
            break
        task = by_name[task_name]
        try:
            rep = evaluate(pat, task)
        except Exception:
            continue
        # only cases that pass every test yet are scored as a different language
        if rep.correctness.accuracy != 1.0:
            continue
        if rep.equivalence.verdict.name != "DIFFERENT":
            continue
        try:
            w = equivalent(pat, task.reference, semantics=Semantics.SEARCH).witness
        except Exception:
            w = None
        out.append({
            "model": model,
            "task": task_name,
            "prompt": task.prompt,
            "model_pattern": pat,
            "gold_pattern": task.reference,
            "witness": w,
            "witness_is_ascii": bool(w) and w.isascii(),
            "positives": list(task.positives)[:4],
            "negatives": list(task.negatives)[:4],
            "verdict": None,  # to be filled: "model_right" | "gold_right" | "ambiguous"
        })

    path = Path(args.out) if args.out else config.RESULTS_DIR / args.run / "disagreements.json"
    path.write_text(json.dumps(out, indent=2))
    ascii_n = sum(1 for o in out if o["witness_is_ascii"])
    print(f"sampled {len(out)} disagreements from {len(pool)} model-task pairs")
    print(f"  {ascii_n} have an ASCII witness (a difference a developer could hit)")
    print(f"  {len(out)-ascii_n} differ only on non-ASCII input (the Unicode-shorthand artifact)")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()

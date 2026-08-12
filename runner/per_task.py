"""Emit per-task outcomes so models can be compared with paired statistics.

Every model saw the same tasks. Comparing them with independent binomial
intervals throws that pairing away and overstates uncertainty badly: task
difficulty dominates the variance, and it is *shared*. A paired analysis
conditions on the task, so only genuine model disagreements carry weight.

With k=3 samples and k=3 reporting, pass@3 for a task reduces to "did any
of the three samples succeed", which is what this records.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

from regexbench import evaluate  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402


def outcomes_for(model: str, run: str, by_name: dict) -> dict:
    rows = [json.loads(x) for x in
            (config.PREDICTIONS_DIR / run / f"{model}.jsonl").read_text().splitlines() if x.strip()]
    samples: dict[str, list[str]] = {}
    for r in rows:
        if r["task_name"].startswith("control/") or r["status"] != "ok" or not r.get("pattern"):
            continue
        samples.setdefault(r["task_name"], []).append(normalize_pattern(r["pattern"])[0])

    out = {}
    for task_name, pats in samples.items():
        task = by_name[task_name]
        any_pass = any_usable = False
        any_vuln = False
        for p in pats:
            try:
                rep = evaluate(p, task)
            except Exception:
                continue
            if rep.correctness.accuracy == 1.0:
                any_pass = True
            if rep.usable:
                any_usable = True
            if rep.safety.risk.name != "SAFE":
                any_vuln = True
        out[task_name] = {"pass": any_pass, "usable": any_usable,
                          "vulnerable": any_vuln, "samples": len(pats)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--models", required=True, help="comma-separated labels")
    args = ap.parse_args()

    by_name = {t.name: t for t in load_regexeval(str(config.require_dataset()))}
    out_dir = config.RESULTS_DIR / args.run / "per_task"
    out_dir.mkdir(parents=True, exist_ok=True)

    for m in [x.strip() for x in args.models.split(",")]:
        res = outcomes_for(m, args.run, by_name)
        (out_dir / f"{m}.json").write_text(json.dumps(res, indent=0, sort_keys=True))
        n = len(res)
        print(f"{m}: {n} tasks | pass {sum(v['pass'] for v in res.values())/n:.1%} "
              f"| usable {sum(v['usable'] for v in res.values())/n:.1%}", flush=True)


if __name__ == "__main__":
    main()

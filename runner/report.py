"""Turn a scored run into the numbers a write-up needs.

Emits the leaderboard table, the headline gaps, and the specific worked
examples that explain what the benchmark measures -- a pattern that
passes every test and is still wrong, and one that passes every test and
can hang a server. Those examples are found in the data rather than
chosen by hand, so the write-up describes the run it actually had.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

from regexbench import Semantics, equivalent, evaluate, screen  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402


def headline(e, metric):
    m = e.get("metrics") or {}
    return next((v for kk, v in m.items() if kk.startswith(metric + "@")), None)


def find_examples(run: str, by_name: dict, limit_models: int = 11):
    """Patterns that pass every test but are wrong, or unsafe."""
    wrong_but_passing, unsafe_but_passing = [], []
    pred_dir = config.PREDICTIONS_DIR / run
    for f in sorted(pred_dir.glob("*.jsonl"))[:limit_models]:
        label = f.stem
        rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        seen = set()
        for r in rows:
            if r["task_name"].startswith("control/") or r["status"] != "ok" or not r["pattern"]:
                continue
            if r["task_name"] in seen:
                continue
            seen.add(r["task_name"])
            task = by_name[r["task_name"]]
            pat = normalize_pattern(r["pattern"])[0]
            try:
                rep = evaluate(pat, task)
            except Exception:
                continue
            if rep.correctness.accuracy < 1.0:
                continue
            if rep.safety.risk.name != "SAFE":
                unsafe_but_passing.append({
                    "model": label, "task": task.name, "prompt": task.prompt,
                    "pattern": pat, "risk": rep.safety.risk.name,
                    "reason": rep.safety.reason,
                })
            elif rep.equivalence.verdict.name == "DIFFERENT":
                try:
                    w = equivalent(pat, task.reference, semantics=Semantics.SEARCH).witness
                except Exception:
                    w = None
                if w:
                    wrong_but_passing.append({
                        "model": label, "task": task.name, "prompt": task.prompt,
                        "pattern": pat, "reference": task.reference, "witness": w,
                        # A non-ASCII witness usually means the only difference is
                        # that \d matches every Unicode digit while [0-9] does not.
                        # True, and a poor illustration: it says more about the
                        # engine's Unicode awareness than about the model. Ranked
                        # below differences a developer would actually hit.
                        "unicode_shorthand_artifact": not w.isascii(),
                    })

    wrong_but_passing.sort(key=lambda e: e["unicode_shorthand_artifact"])
    return wrong_but_passing, unsafe_but_passing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    summary = json.loads((config.RESULTS_DIR / args.run / "summary.json").read_text())
    by_name = {t.name: t for t in load_regexeval(str(config.require_dataset()))}

    rows = []
    for e in summary:
        rows.append({
            "model": e["model"],
            "slug": e["model_requested"],
            "provider": ", ".join(e.get("providers_resolved") or []),
            "usable": headline(e, "usable"),
            "pass": headline(e, "pass"),
            "vulnerable": headline(e, "vulnerable"),
            "dfa_eq": headline(e, "dfa-eq"),
            "failures": e["response_failures"],
            "attempted": e["tasks_attempted"],
            "cost_per_task": e["cost_usd_per_task"],
            "cost_total": e["cost_usd_total"],
            "k": e["k"],
            "controls_ok": e["controls_all_as_expected"],
        })

    wrong, unsafe = find_examples(args.run, by_name)
    scored = [r for r in rows if r["usable"] is not None]
    out = {
        "run": args.run,
        "models": len(rows),
        "k": rows[0]["k"] if rows else None,
        "total_cost": round(sum(r["cost_total"] for r in rows), 4),
        "total_calls": sum(r["attempted"] for r in rows),
        "total_failures": sum(r["failures"] for r in rows),
        "all_controls_ok": all(r["controls_ok"] for r in rows),
        "table": rows,
        "best_usable": max((r["usable"] for r in scored), default=None),
        "best_pass": max((r["pass"] for r in scored), default=None),
        "biggest_gap": max(
            ((r["pass"] - r["usable"], r["model"]) for r in scored), default=None
        ),
        "example_wrong_but_passing": wrong[:8],
        "wrong_substantive_count": sum(1 for e in wrong if not e["unicode_shorthand_artifact"]),
        "wrong_unicode_only_count": sum(1 for e in wrong if e["unicode_shorthand_artifact"]),
        "example_unsafe_but_passing": unsafe[:8],
    }
    path = Path(args.out) if args.out else config.RESULTS_DIR / args.run / "report.json"
    path.write_text(json.dumps(out, indent=2))

    print(f"{'model':26s} {'usable':>7s} {'pass':>7s} {'vuln':>7s} {'dfa-eq':>7s} {'fails':>9s} {'$/task':>9s}")
    print("-" * 82)
    for r in rows:
        f = lambda v: "  --" if v is None else f"{v:.1%}"
        cpt = "--" if r["cost_per_task"] is None else f"{r['cost_per_task']:.6f}"
        print(f"{r['model']:26s} {f(r['usable']):>7s} {f(r['pass']):>7s} {f(r['vulnerable']):>7s} "
              f"{f(r['dfa_eq']):>7s} {r['failures']:>4d}/{r['attempted']:<4d} {cpt:>9s}")
    print(f"\ntotal ${out['total_cost']:.4f} over {out['total_calls']} calls, "
          f"{out['total_failures']} failures, controls_ok={out['all_controls_ok']}")
    substantive = sum(1 for e in wrong if not e["unicode_shorthand_artifact"])
    print(f"examples found: {len(wrong)} passing-but-wrong "
          f"({substantive} substantive, {len(wrong) - substantive} unicode-shorthand only), "
          f"{len(unsafe)} passing-but-unsafe")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()

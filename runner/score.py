"""Score committed predictions with regexbench.

Reads only files in predictions/ -- no network, no API key, no cost. That
is deliberate: anyone can clone this repo and recompute every published
number offline, and CI does exactly that on every push.

One headline score per model. Patterns are normalized before scoring (see
"the wrapper rule" in METHODOLOGY.md); the unnormalized score is also
recorded in the per-model JSON so the choice is auditable, but it is not
what the leaderboard reports.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

from regexbench import run  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402

CONTROL_EXPECTATIONS = {
    "control/good": lambda m: m["pass@1"] == 1.0 and m["usable@1"] == 1.0,
    "control/bad": lambda m: m["pass@1"] == 0.0 and m["usable@1"] == 0.0,
    "control/vulnerable": lambda m: m["vulnerable@1"] == 1.0,
}


def metrics_of(rep) -> dict:
    """Headline three first; the rest are kept for the appendix."""
    return {
        "usable@1": rep.usable_at(1),
        "pass@1": rep.pass_at(1),
        "vulnerable@1": rep.vulnerable_at(1),
        # appendix metrics -- not shown on the leaderboard front page
        "dfa-eq@1": rep.dfa_eq_at(1),
        "dfa-eq@1 (decided)": rep.dfa_eq_decided_at(1),
        "exact@1": rep.exact_at(1),
        "undecided": rep.undecided,
    }


def score_run(run_name: str) -> list[dict]:
    dataset = config.require_dataset()
    pred_dir = config.PREDICTIONS_DIR / run_name
    result_dir = config.RESULTS_DIR / run_name
    if not pred_dir.is_dir():
        raise SystemExit(f"No predictions at {pred_dir}")
    result_dir.mkdir(parents=True, exist_ok=True)

    by_name = {t.name: t for t in load_regexeval(str(dataset))}
    summary = []

    for pred_file in sorted(pred_dir.glob("*.jsonl")):
        label = pred_file.stem
        rows = [json.loads(x) for x in pred_file.read_text().splitlines() if x.strip()]
        controls = [r for r in rows if r["task_name"].startswith("control/")]
        task_rows = [r for r in rows if not r["task_name"].startswith("control/")]

        # Controls ride the identical scoring path. A scorer returning zeros
        # looks exactly like a model that failed; these tell them apart.
        control_report = {}
        controls_ok = True
        for cr in controls:
            base = by_name[cr["base_task"]]
            rep = run([base], {base.name: cr["pattern"]}, name=cr["task_name"])
            got = {
                "pattern": cr["pattern"],
                "base_task": base.name,
                "pass@1": rep.pass_at(1),
                "usable@1": rep.usable_at(1),
                "vulnerable@1": rep.vulnerable_at(1),
            }
            got["as_expected"] = CONTROL_EXPECTATIONS[cr["task_name"]](got)
            controls_ok &= got["as_expected"]
            control_report[cr["task_name"]] = got

        answered = [r for r in task_rows if r["status"] == "ok" and r["pattern"]]
        failed = [r for r in task_rows if not (r["status"] == "ok" and r["pattern"])]
        tasks = [by_name[r["task_name"]] for r in answered]

        as_sent = {r["task_name"]: r["pattern"] for r in answered}
        normalized, wrapped = {}, {}
        for r in answered:
            pat, notes = normalize_pattern(r["pattern"])
            normalized[r["task_name"]] = pat
            if notes:
                wrapped[r["task_name"]] = {"as_sent": r["pattern"], "scored": pat}

        rep = run(tasks, normalized, name=label) if tasks else None
        rep_as_sent = run(tasks, as_sent, name=f"{label} (as sent)") if tasks else None

        cost = sum(r.get("cost_usd") or 0.0 for r in task_rows)
        entry = {
            "model": label,
            "model_requested": task_rows[0]["model_requested"] if task_rows else None,
            "provider_requested": task_rows[0]["provider_requested"] if task_rows else None,
            "providers_resolved": sorted(
                {r["provider_resolved"] for r in answered if r["provider_resolved"]}
            ),
            "regexbench_version": config.REGEXBENCH_VERSION,
            "regexbench_commit": config.REGEXBENCH_COMMIT,
            "python_version": sys.version.split()[0],
            "dataset": "Re(gEx|DoS)Eval",
            "k": 1,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
            "tasks_attempted": len(task_rows),
            "tasks_answered": len(answered),
            "response_failures": len(failed),
            "failure_detail": [
                {"task": r["task_name"], "status": r["status"], "error": (r.get("error") or "")[:300]}
                for r in failed
            ],
            "wrapped_responses": len(wrapped),
            "wrapped_detail": wrapped,
            "cost_usd_total": round(cost, 8),
            "cost_usd_per_task": round(cost / len(task_rows), 8) if task_rows else None,
            "completion_tokens_total": sum(
                (r.get("usage") or {}).get("completion_tokens", 0) for r in task_rows
            ),
            "controls_all_as_expected": controls_ok,
            "controls": control_report,
            "metrics": metrics_of(rep) if rep else None,
            "metrics_as_sent": metrics_of(rep_as_sent) if rep_as_sent else None,
            "table": rep.table(ks=(1,)) if rep else None,
        }
        (result_dir / f"{label}.json").write_text(json.dumps(entry, indent=2, sort_keys=True))
        summary.append(entry)

    summary.sort(key=lambda e: (-(e["metrics"] or {}).get("usable@1", -1), e["model"]))
    (result_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def print_summary(summary: list[dict]) -> None:
    print(f"{'model':34s} {'usable@1':>9s} {'pass@1':>8s} {'vuln@1':>8s} {'fails':>7s} {'$/task':>10s}")
    print("-" * 82)
    for e in summary:
        m = e["metrics"]
        fails = f"{e['response_failures']}/{e['tasks_attempted']}"
        if m is None:
            print(f"{e['model']:34s} {'--':>9s} {'--':>8s} {'--':>8s} {fails:>7s} {'--':>10s}")
            continue
        print(
            f"{e['model']:34s} {m['usable@1']:8.1%} {m['pass@1']:7.1%} "
            f"{m['vulnerable@1']:7.1%} {fails:>7s} {e['cost_usd_per_task']:10.6f}"
        )
    bad = [e["model"] for e in summary if not e["controls_all_as_expected"]]
    print()
    print(f"controls as expected: {'ALL OK' if not bad else 'FAILED for ' + ', '.join(bad)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="preview", help="subdirectory of predictions/ to score")
    ap.add_argument(
        "--check",
        action="store_true",
        help="fail if recomputed scores differ from the committed results/ (used by CI)",
    )
    args = ap.parse_args()

    committed_path = config.RESULTS_DIR / args.run / "summary.json"
    committed = json.loads(committed_path.read_text()) if committed_path.exists() else None

    summary = score_run(args.run)
    print_summary(summary)

    if args.check:
        if committed is None:
            raise SystemExit(f"--check: nothing committed at {committed_path}")
        drift = []
        old = {e["model"]: e.get("metrics") for e in committed}
        for e in summary:
            if old.get(e["model"]) != e.get("metrics"):
                drift.append(e["model"])
        if drift:
            print(f"\nFAIL: recomputed scores differ from committed results for: {', '.join(drift)}")
            raise SystemExit(1)
        print("\nOK: recomputed scores match the committed results exactly.")

    if any(not e["controls_all_as_expected"] for e in summary):
        raise SystemExit("FAIL: a control did not behave as expected -- results not publishable")


if __name__ == "__main__":
    main()

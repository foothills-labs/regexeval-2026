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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

from regexbench import run  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402

# Scoring runs DFA equivalence and an empirical ReDoS pass per pattern, both
# of which are CPU-bound and can block on a pathological pattern until the
# match timeout. Parallel across tasks keeps a full sweep tractable.
WORKERS = max(1, (os.cpu_count() or 4) - 1)

CONTROL_EXPECTATIONS = {
    "control/good": lambda m: m["pass@1"] == 1.0 and m["usable@1"] == 1.0,
    "control/bad": lambda m: m["pass@1"] == 0.0 and m["usable@1"] == 0.0,
    "control/vulnerable": lambda m: m["vulnerable@1"] == 1.0,
}


def metrics_of(rep, k: int = 1) -> dict:
    """Headline three first; the rest are kept for the appendix."""
    return {
        f"usable@{k}": rep.usable_at(k),
        f"pass@{k}": rep.pass_at(k),
        f"vulnerable@{k}": rep.vulnerable_at(k),
        # appendix metrics -- not shown on the leaderboard front page
        f"dfa-eq@{k}": rep.dfa_eq_at(k),
        f"dfa-eq@{k} (decided)": rep.dfa_eq_decided_at(k),
        f"exact@{k}": rep.exact_at(k),
        "undecided": rep.undecided,
    }


def rebuild_summary(run_name: str) -> list[dict]:
    """Reassemble summary.json from the per-model result files.

    Scoring is CPU-bound and one process per model is far faster than one
    process for all of them, so models can be scored separately and merged
    here. The summary is derived from the per-model files either way, so a
    merged run and a single run produce the same summary.
    """
    result_dir = config.RESULTS_DIR / run_name
    entries = [
        json.loads(f.read_text())
        for f in sorted(result_dir.glob("*.json"))
        if f.name != "summary.json"
    ]
    entries.sort(key=lambda e: (-(headline(e, "usable")
                                 if headline(e, "usable") is not None else -1), e["model"]))
    (result_dir / "summary.json").write_text(json.dumps(entries, indent=2, sort_keys=True))
    return entries


def headline(e, metric):
    m = e.get("metrics") or {}
    return next((v for kk, v in m.items() if kk.startswith(metric + "@")), None)


def score_run(run_name: str, only: set[str] | None = None) -> list[dict]:
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
        if only and label not in only:
            continue
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

        # Group the k samples per task into a list, in sample order. A task
        # whose samples partly failed is scored on the ones that came back --
        # the failures are still counted in response_failures.
        as_sent, normalized, wrapped = {}, {}, {}
        for r in sorted(answered, key=lambda r: (r["task_name"], r.get("sample", 0))):
            name = r["task_name"]
            as_sent.setdefault(name, []).append(r["pattern"])
            pat, notes = normalize_pattern(r["pattern"])
            normalized.setdefault(name, []).append(pat)
            if notes:
                wrapped.setdefault(name, []).append({"as_sent": r["pattern"], "scored": pat})

        tasks = [by_name[n] for n in normalized]
        k_actual = max((len(v) for v in normalized.values()), default=0)

        rep = run(tasks, normalized, name=label, workers=WORKERS) if tasks else None
        # Only worth scoring the unnormalized set when normalization actually
        # changed something. When no response was wrapped the two are the same
        # inputs, and scoring them twice doubles a CPU-bound run for nothing.
        rep_as_sent = (
            run(tasks, as_sent, name=f"{label} (as sent)", workers=WORKERS)
            if tasks and wrapped else None
        )

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
            "k": k_actual,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
            "tasks_attempted": len(task_rows),
            "tasks_answered": len(answered),
            "response_failures": len(failed),
            "failure_detail": [
                {"task": r["task_name"], "status": r["status"], "error": (r.get("error") or "")[:300]}
                for r in failed
            ],
            "wrapped_responses": sum(len(v) for v in wrapped.values()),
            "wrapped_detail": wrapped,
            "cost_usd_total": round(cost, 8),
            "cost_usd_per_task": round(cost / len(task_rows), 8) if task_rows else None,
            "completion_tokens_total": sum(
                (r.get("usage") or {}).get("completion_tokens", 0) for r in task_rows
            ),
            "controls_all_as_expected": controls_ok,
            "controls": control_report,
            "metrics": metrics_of(rep, k_actual) if rep else None,
            "metrics_as_sent": (
                metrics_of(rep_as_sent, k_actual) if rep_as_sent
                else (metrics_of(rep, k_actual) if rep else None)
            ),
            "table": rep.table(ks=(k_actual,)) if rep else None,
        }
        (result_dir / f"{label}.json").write_text(json.dumps(entry, indent=2, sort_keys=True))
        summary.append(entry)

    summary.sort(key=lambda e: (-(headline(e, "usable") if headline(e, "usable") is not None else -1),
                                e["model"]))
    (result_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def print_summary(summary: list[dict]) -> None:
    ks = {e["k"] for e in summary if e.get("k")}
    kl = str(next(iter(ks))) if len(ks) == 1 else "k"
    print(f"{'model':34s} {'usable@'+kl:>9s} {'pass@'+kl:>8s} {'vuln@'+kl:>8s} "
          f"{'fails':>7s} {'$/task':>10s}")
    print("-" * 82)
    def pick(m, metric):
        return next((v for kk, v in m.items() if kk.startswith(metric + "@")), None)

    for e in summary:
        m = e["metrics"]
        fails = f"{e['response_failures']}/{e['tasks_attempted']}"
        if m is None:
            print(f"{e['model']:34s} {'--':>9s} {'--':>8s} {'--':>8s} {fails:>7s} {'--':>10s}")
            continue
        print(
            f"{e['model']:34s} {pick(m,'usable'):8.1%} {pick(m,'pass'):7.1%} "
            f"{pick(m,'vulnerable'):7.1%} {fails:>7s} {e['cost_usd_per_task']:10.6f}"
        )
    bad = [e["model"] for e in summary if not e["controls_all_as_expected"]]
    print()
    print(f"controls as expected: {'ALL OK' if not bad else 'FAILED for ' + ', '.join(bad)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="preview", help="subdirectory of predictions/ to score")
    ap.add_argument("--models", default=None,
                    help="comma-separated labels; score only these (for parallel scoring)")
    ap.add_argument("--merge", action="store_true",
                    help="rebuild summary.json from existing per-model result files and exit")
    ap.add_argument(
        "--check",
        action="store_true",
        help="fail if recomputed scores differ from the committed results/ (used by CI)",
    )
    args = ap.parse_args()

    if args.merge:
        summary = rebuild_summary(args.run)
        print_summary(summary)
        if any(not e["controls_all_as_expected"] for e in summary):
            raise SystemExit("FAIL: a control did not behave as expected")
        return

    committed_path = config.RESULTS_DIR / args.run / "summary.json"
    committed = json.loads(committed_path.read_text()) if committed_path.exists() else None

    only = {m.strip() for m in args.models.split(",")} if args.models else None
    summary = score_run(args.run, only)
    if only:
        # A partial run must not overwrite the whole-run summary.
        print_summary(summary)
        print(f"\nscored {len(summary)} model(s); run --merge to rebuild summary.json")
        return
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

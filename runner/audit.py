"""Pre-launch audit: is this run trustworthy enough to publish?

Checks the things that would make a sweep quietly wrong rather than
visibly broken. Exits non-zero if any BLOCKER fires.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

BLOCKER, WARN, OK = "BLOCKER", "WARN", "OK"


def audit(run: str, k_expected: int, task_count: int | None):
    pred_dir = config.PREDICTIONS_DIR / run
    findings = []
    per_model = {}

    for f in sorted(pred_dir.glob("*.jsonl")):
        label = f.stem
        rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        real = [r for r in rows if not r["task_name"].startswith("control/")]
        ctrl = [r for r in rows if r["task_name"].startswith("control/")]
        ok = [r for r in real if r["status"] == "ok" and r.get("pattern")]
        bad = [r for r in real if not (r["status"] == "ok" and r.get("pattern"))]

        providers = Counter(r["provider_resolved"] for r in ok if r.get("provider_resolved"))
        statuses = Counter(r["status"] for r in real)
        cost = sum(r.get("cost_usd") or 0.0 for r in real)
        reasoning_tok = sum(r.get("reasoning_tokens") or 0 for r in real)
        tasks = {r["task_name"] for r in real}
        samples = Counter(r["task_name"] for r in real)
        wrapped = sum(1 for r in ok if normalize_pattern(r["pattern"])[1])
        empties = sum(1 for r in real if r["status"] == "parse_failure")

        per_model[label] = {
            "attempted": len(real), "ok": len(ok), "failed": len(bad),
            "tasks": len(tasks), "providers": dict(providers), "statuses": dict(statuses),
            "cost": cost, "reasoning_tokens": reasoning_tok, "wrapped": wrapped,
            "empty_content": empties, "controls": len(ctrl),
            "cost_per_call": cost / len(ok) if ok else None,
        }

        # --- the checks ---
        if not ok:
            findings.append((BLOCKER, label, f"no usable responses at all ({len(bad)} failed)"))
        elif len(bad) / max(len(real), 1) > 0.05:
            findings.append((WARN, label, f"{len(bad)}/{len(real)} requests failed"))

        if len(providers) > 1:
            findings.append((BLOCKER, label,
                             f"served by MULTIPLE providers {dict(providers)} -- pin did not hold"))

        if reasoning_tok > 0:
            findings.append((BLOCKER, label,
                             f"{reasoning_tok} reasoning tokens billed despite reasoning=off"))

        if empties:
            findings.append((BLOCKER, label, f"{empties} empty-content responses"))

        wrong_k = {t: c for t, c in samples.items() if c != k_expected}
        if wrong_k:
            findings.append((WARN, label,
                             f"{len(wrong_k)} task(s) do not have exactly k={k_expected} samples"))

        if task_count and len(tasks) != task_count:
            findings.append((WARN, label, f"covered {len(tasks)} tasks, expected {task_count}"))

        if len(ctrl) != 3:
            findings.append((BLOCKER, label, f"{len(ctrl)} controls present, expected 3"))

        # identical samples means k is buying nothing
        by_task = {}
        for r in ok:
            by_task.setdefault(r["task_name"], []).append(r["pattern"])
        if by_task:
            identical = sum(1 for v in by_task.values() if len(v) > 1 and len(set(v)) == 1)
            frac = identical / len(by_task)
            if frac > 0.9:
                findings.append((WARN, label,
                                 f"{frac:.0%} of tasks returned k identical samples -- "
                                 f"k is buying little diversity at this temperature"))

    return findings, per_model


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="pilot")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--tasks", type=int, default=None)
    ap.add_argument("--project-to", type=int, default=None,
                    help="extrapolate cost to this many tasks at the same k")
    args = ap.parse_args()

    findings, per_model = audit(args.run, args.k, args.tasks)

    print(f"{'model':26s} {'ok':>5s} {'fail':>5s} {'provider':>22s} {'$/call':>10s} {'wrapped':>8s}")
    print("-" * 82)
    for label, s in per_model.items():
        prov = ",".join(s["providers"]) or "-"
        cpc = f"{s['cost_per_call']:.6f}" if s["cost_per_call"] else "-"
        print(f"{label:26s} {s['ok']:5d} {s['failed']:5d} {prov:>22s} {cpc:>10s} {s['wrapped']:8d}")

    total = sum(s["cost"] for s in per_model.values())
    print(f"\npilot spend: ${total:.4f}")

    if args.project_to:
        print(f"\nprojected full sweep ({args.project_to} tasks x k={args.k}):")
        grand = 0.0
        for label, s in per_model.items():
            if not s["cost_per_call"]:
                print(f"  {label:26s}  -- no data")
                continue
            proj = s["cost_per_call"] * args.project_to * args.k
            grand += proj
            print(f"  {label:26s} ${proj:7.2f}")
        print(f"  {'TOTAL':26s} ${grand:7.2f}")

    print()
    order = {BLOCKER: 0, WARN: 1}
    findings.sort(key=lambda f: order.get(f[0], 2))
    if not findings:
        print("AUDIT CLEAN -- no blockers, no warnings.")
        return
    for level, label, msg in findings:
        print(f"  [{level:7s}] {label}: {msg}")
    if any(f[0] == BLOCKER for f in findings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

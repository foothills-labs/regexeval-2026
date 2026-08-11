"""Score the preview predictions with regexbench and emit the results JSON.

Scores every model twice from the same committed responses:

  strict     -- the pattern exactly as the model emitted it
  normalized -- with host-language quoting (r'...', backticks, /.../ )
                stripped first

The gap between the two is a harness artifact, not a capability
difference, so both are reported and the number of normalized responses
is stated. Re-scoring reads only the committed raw responses, so it costs
nothing and is reproducible offline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from openrouter_client import normalize_pattern  # noqa: E402

sys.path.insert(
    0, "/tmp/claude-0/-home-user-regexleaderboard/4f381924-048f-55c1-baa3-50487ddcdad5/scratchpad"
)
from regexbench import run  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATASET = Path(
    "/tmp/claude-0/-home-user-regexleaderboard/4f381924-048f-55c1-baa3-50487ddcdad5"
    "/scratchpad/RegexEval.json"
)
PRED_DIR = REPO / "predictions" / "preview"
RESULT_DIR = REPO / "results" / "preview"

REGEXBENCH_COMMIT = "05d7547b1a71e6dd5cb00d71bf4dac7732be3ecd"


def metrics_of(rep) -> dict:
    return {
        "pass@1": rep.pass_at(1),
        "dfa-eq@1": rep.dfa_eq_at(1),
        "dfa-eq@1 (decided)": rep.dfa_eq_decided_at(1),
        "exact@1": rep.exact_at(1),
        "usable@1": rep.usable_at(1),
        "vulnerable@1": rep.vulnerable_at(1),
        "undecided": rep.undecided,
    }


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    all_tasks = load_regexeval(str(DATASET))
    by_name = {t.name: t for t in all_tasks}

    summary = []
    for pred_file in sorted(PRED_DIR.glob("*.jsonl")):
        label = pred_file.stem
        rows = [json.loads(x) for x in pred_file.read_text().splitlines() if x.strip()]

        control_rows = [r for r in rows if r["task_name"].startswith("control/")]
        task_rows = [r for r in rows if not r["task_name"].startswith("control/")]

        # --- controls: these must come back good=pass, bad=fail, vuln=flagged ---
        control_report = {}
        controls_ok = True
        for cr in control_rows:
            base = by_name[cr["base_task"]]
            rep = run([base], {base.name: cr["pattern"]}, name=cr["task_name"])
            got = {
                "pattern": cr["pattern"],
                "base_task": base.name,
                "pass@1": rep.pass_at(1),
                "usable@1": rep.usable_at(1),
                "vulnerable@1": rep.vulnerable_at(1),
            }
            expected = {
                "control/good": got["pass@1"] == 1.0 and got["usable@1"] == 1.0,
                "control/bad": got["pass@1"] == 0.0 and got["usable@1"] == 0.0,
                "control/vulnerable": got["vulnerable@1"] == 1.0,
            }[cr["task_name"]]
            got["as_expected"] = expected
            controls_ok = controls_ok and expected
            control_report[cr["task_name"]] = got

        answered = [r for r in task_rows if r["status"] == "ok" and r["pattern"]]
        failed = [r for r in task_rows if not (r["status"] == "ok" and r["pattern"])]
        scored_tasks = [by_name[r["task_name"]] for r in answered]

        strict_preds = {r["task_name"]: r["pattern"] for r in answered}
        norm_preds = {}
        norm_notes = {}
        for r in answered:
            n, notes = normalize_pattern(r["pattern"])
            norm_preds[r["task_name"]] = n
            if notes:
                norm_notes[r["task_name"]] = {"raw": r["pattern"], "normalized": n}

        if scored_tasks:
            rep_strict = run(scored_tasks, strict_preds, name=f"{label} (strict)")
            rep_norm = run(scored_tasks, norm_preds, name=f"{label} (normalized)")
        else:
            rep_strict = rep_norm = None

        total_cost = sum(r.get("cost_usd") or 0.0 for r in task_rows)
        completion_tokens = sum(
            (r.get("usage") or {}).get("completion_tokens", 0) for r in task_rows
        )

        entry = {
            "model": label,
            "model_requested": task_rows[0]["model_requested"] if task_rows else None,
            "provider_requested": task_rows[0]["provider_requested"] if task_rows else None,
            "providers_resolved": sorted(
                {r["provider_resolved"] for r in answered if r["provider_resolved"]}
            ),
            "models_resolved": sorted(
                {r["model_resolved"] for r in answered if r.get("model_resolved")}
            ),
            "regexbench_version": __import__("regexbench").__version__,
            "regexbench_commit": REGEXBENCH_COMMIT,
            "python_version": sys.version.split()[0],
            "dataset": "Re(gEx|DoS)Eval",
            "k": 1,
            "temperature": 0.0,
            "max_tokens": 200,
            "tasks_attempted": len(task_rows),
            "tasks_answered": len(answered),
            "response_failures": len(failed),
            "failure_detail": [
                {
                    "task": r["task_name"],
                    "status": r["status"],
                    "error": (r.get("error") or "")[:300],
                }
                for r in failed
            ],
            "wrapped_responses": len(norm_notes),
            "wrapped_detail": norm_notes,
            "cost_usd_total": round(total_cost, 8),
            "cost_usd_per_task": round(total_cost / len(task_rows), 8) if task_rows else None,
            "completion_tokens_total": completion_tokens,
            "controls_all_as_expected": controls_ok,
            "controls": control_report,
            "metrics_strict": metrics_of(rep_strict) if rep_strict else None,
            "metrics_normalized": metrics_of(rep_norm) if rep_norm else None,
            "table_strict": rep_strict.table(ks=(1,)) if rep_strict else None,
            "table_normalized": rep_norm.table(ks=(1,)) if rep_norm else None,
        }

        (RESULT_DIR / f"{label}.json").write_text(json.dumps(entry, indent=2))
        summary.append(entry)

        print(f"=== {label} ===")
        print(f"controls all as expected: {controls_ok}")
        if rep_strict is None:
            print(f"  NO SCORABLE PREDICTIONS -- {len(failed)}/{len(task_rows)} requests failed")
            for f in entry["failure_detail"][:2]:
                print(f"    {f['task']}: {f['status']} {f['error'][:160]}")
            print()
            continue
        print(rep_strict.table(ks=(1,)))
        if entry["wrapped_responses"]:
            print(f"  [{entry['wrapped_responses']} response(s) wrapped -> normalized]")
            print(rep_norm.table(ks=(1,)))
        print(
            f"  cost ${entry['cost_usd_total']:.6f} total, "
            f"${entry['cost_usd_per_task']:.6f}/task, failures {len(failed)}"
        )
        print()

    (RESULT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"wrote {RESULT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()

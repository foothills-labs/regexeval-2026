"""Collect predictions from every model in models.json.

Resumable: results are keyed by (model, task, sample index) and appended to
predictions/<run>/<model>.jsonl. Re-running skips work already on disk, so
an interrupted sweep costs nothing to continue and a failed model can be
re-run alone.

Costs money. `make score` does not.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import call, extract_pattern  # noqa: E402

from regexbench.datasets import load_regexeval  # noqa: E402

ROSTER = json.loads((Path(__file__).parent / "models.json").read_text())

CONTROLS = [
    ("control/good", None),        # filled with the task's own reference
    ("control/bad", "z{5}"),
    ("control/vulnerable", "(a+)+b"),
]


def build_prompt(task) -> str:
    return (
        f"{task.prompt}\n\n"
        "Reply with only the regular expression pattern in a single fenced "
        "code block."
    )


def select_tasks(all_tasks, limit: int | None):
    """Evenly spread across the corpus, so a subset isn't all easy tasks."""
    if limit is None or limit >= len(all_tasks):
        return all_tasks
    step = len(all_tasks) / limit
    return [all_tasks[int(i * step)] for i in range(limit)]


def load_done(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        done.add((r["task_name"], r.get("sample", 0)))
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep", help="output subdirectory")
    ap.add_argument("--limit", type=int, default=None, help="number of tasks (default: all)")
    ap.add_argument("--k", type=int, default=None, help="samples per task")
    ap.add_argument("--models", default=None, help="comma-separated labels; default all")
    ap.add_argument("--reasoning", choices=["off", "on"], default="off")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()

    d = ROSTER["defaults"]
    k = args.k or d["k"]
    reasoning = {"enabled": False} if args.reasoning == "off" else None

    models = ROSTER["models"]
    if args.models:
        want = {m.strip() for m in args.models.split(",")}
        models = [m for m in models if m["label"] in want]
        missing = want - {m["label"] for m in models}
        if missing:
            raise SystemExit(f"unknown model label(s): {', '.join(sorted(missing))}")

    tasks = select_tasks(load_regexeval(str(config.require_dataset())), args.limit)
    out_dir = config.PREDICTIONS_DIR / args.run
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(models) * len(tasks) * k
    print(
        f"plan: {len(models)} models x {len(tasks)} tasks x k={k} = {total} calls | "
        f"reasoning={args.reasoning} temp={d['temperature']} max_tokens={d['max_tokens']}"
    )
    if args.dry_run:
        for m in models:
            print(f"  {m['label']:24s} {m['slug']:38s} pin={m['provider'].get('order')}")
        return

    grand_cost = 0.0
    for m in models:
        out_path = out_dir / f"{m['label']}.jsonl"
        done = load_done(out_path)
        wrote = 0
        model_cost = 0.0
        print(f"\n=== {m['label']} ({m['slug']}) ===", flush=True)

        with out_path.open("a") as fh:
            # controls are synthetic -- no API call, but they ride the same file
            for cname, cpattern in CONTROLS:
                if (cname, 0) in done:
                    continue
                base = tasks[0] if cname == "control/good" else tasks[min(1, len(tasks) - 1)]
                pattern = base.reference if cpattern is None else cpattern
                fh.write(json.dumps({
                    "task_name": cname, "base_task": base.name, "sample": 0,
                    "model_requested": m["slug"], "provider_requested": m["provider"],
                    "status": "ok", "provider_resolved": "n/a (synthetic control)",
                    "model_resolved": "n/a", "content": pattern, "pattern": pattern,
                    "usage": {}, "cost_usd": 0.0, "latency_s": 0.0, "generation_id": None,
                }) + "\n")

            for task in tasks:
                for sample in range(k):
                    if (task.name, sample) in done:
                        continue
                    res = call(
                        model=m["slug"], provider=m["provider"], prompt=build_prompt(task),
                        temperature=d["temperature"], max_tokens=d["max_tokens"],
                        reasoning=reasoning,
                    )
                    usage = res.usage or {}
                    ctd = usage.get("completion_tokens_details") or {}
                    fh.write(json.dumps({
                        "task_name": task.name, "sample": sample,
                        "model_requested": res.model_requested,
                        "provider_requested": res.provider_requested,
                        "status": res.status,
                        "provider_resolved": res.provider_resolved,
                        "model_resolved": res.model_resolved,
                        "content": res.content,
                        "pattern": extract_pattern(res.content) if res.ok else None,
                        "usage": usage,
                        "reasoning_tokens": ctd.get("reasoning_tokens"),
                        "cost_usd": res.cost_usd, "latency_s": round(res.latency_s, 2),
                        "generation_id": res.generation_id, "error": res.error,
                    }) + "\n")
                    fh.flush()
                    model_cost += res.cost_usd or 0.0
                    wrote += 1
                    if not res.ok:
                        print(f"  ! {task.name} s{sample}: {res.status} {(res.error or '')[:90]}",
                              flush=True)
                    time.sleep(0.2)

        grand_cost += model_cost
        print(f"  {wrote} new call(s), ${model_cost:.4f}", flush=True)

    print(f"\nTOTAL THIS RUN: ${grand_cost:.4f}")


if __name__ == "__main__":
    main()

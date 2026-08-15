"""Second-corpus replication: collect predictions on StructuredRegex.

The main sweep measures three axes on one corpus. Two of those axes never
consult the reference at all, so they can be replicated anywhere that supplies
test strings. StructuredRegex (Ye et al., ACL 2020) does: every instance ships
positive and negative example strings alongside the description.

Its own reference regexes are in a prefix DSL (`concat(repeatatleast(<h>,3),...)`)
and are deliberately NOT used here. That means no dfa-eq and no exact match on
this corpus, which is fine: those are the reference-dependent metrics this
paper argues against trusting. What we get is pass@1 and vulnerable@1, both
computed without a reference.

Resumable and fingerprinted on the same terms as sweep.py. Refuses to exceed
--max-spend. Costs money; scoring does not.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import call, extract_pattern  # noqa: E402

ROSTER = json.loads((Path(__file__).parent / "models.json").read_text())

# Self-contained controls. Unlike sweep.py these cannot borrow a task's own
# reference, because this corpus's references are in a DSL. Each carries its
# own strings so the scorer can check it without consulting anything.
CONTROLS = [
    {"name": "control/good", "pattern": "^[0-9]$", "pos": ["7"], "neg": ["77", "a"]},
    {"name": "control/bad", "pattern": "z{5}", "pos": ["7"], "neg": ["77", "a"]},
    {"name": "control/vulnerable", "pattern": "(a+)+b", "pos": ["aab"], "neg": ["aac"]},
]


def load_tasks(path: Path):
    """Instances that carry both positive and negative strings.

    Seven of the 629 rows are missing one side or the other; pass@k is not
    defined for them, so they are dropped rather than scored on half a test.
    """
    tasks, skipped = [], 0
    with path.open() as fh:
        for i, row in enumerate(csv.DictReader(fh, delimiter="\t")):
            pos = row["pos_examples"].split()
            neg = row["neg_examples"].split()
            if not pos or not neg:
                skipped += 1
                continue
            tasks.append({
                "name": f'{row["problem_id"]}#{i}',
                "prompt": row["description"].strip(),
                "pos": pos,
                "neg": neg,
            })
    return tasks, skipped


def build_prompt(task) -> str:
    return (
        f'{task["prompt"]}\n\n'
        "Reply with only the regular expression pattern in a single fenced "
        "code block."
    )


def config_fingerprint(model, d, reasoning) -> str:
    """Same guard as the main sweep: a resume must not mix configurations."""
    payload = json.dumps({
        "slug": model["slug"],
        "provider": model["provider"],
        "max_tokens": d["max_tokens"],
        "temperature": d.get("temperature"),
        "reasoning": reasoning,
        "corpus": "structuredregex/testi",
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_done(path: Path, fingerprint: str):
    done, foreign = set(), 0
    if not path.exists():
        return done, foreign
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("config") != fingerprint:
            foreign += 1
            continue
        done.add((row["task_name"], row["sample"]))
    return done, foreign


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="path to testi.tsv")
    ap.add_argument("--run", default="structuredregex")
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--max-spend", type=float, required=True,
                    help="hard ceiling in USD; the run stops rather than exceed it")
    ap.add_argument("--models", default=None, help="comma-separated labels")
    args = ap.parse_args()

    tasks, skipped = load_tasks(Path(args.corpus))
    if args.limit:
        tasks = tasks[:args.limit]
    models = ROSTER["models"] if isinstance(ROSTER, dict) else ROSTER
    if args.models:
        want = {s.strip() for s in args.models.split(",")}
        models = [m for m in models if m["label"] in want]

    d = {"temperature": None, "max_tokens": args.max_tokens}
    reasoning = {"enabled": False}

    out_dir = config.PREDICTIONS_DIR / args.run
    out_dir.mkdir(parents=True, exist_ok=True)

    planned = len(tasks) * args.k * len(models)
    print(f"corpus     : {args.corpus}")
    print(f"tasks      : {len(tasks)} ({skipped} dropped for missing pos/neg strings)")
    print(f"models     : {len(models)}   k={args.k}   planned calls: {planned}")
    print(f"config     : reasoning=off temperature=None max_tokens={args.max_tokens}")
    print(f"spend cap  : ${args.max_spend:.2f}")
    print(f"output     : {out_dir}\n")

    grand = 0.0
    stopped = False
    for m in models:
        if stopped:
            break
        out_path = out_dir / f"{m['label']}.jsonl"
        fp = config_fingerprint(m, d, reasoning)
        done, foreign = load_done(out_path, fp)
        if foreign:
            raise SystemExit(
                f"\n{m['label']}: {out_path} holds {foreign} row(s) from a different "
                f"configuration. Delete it or use a new --run name."
            )
        wrote, model_cost, failures = 0, 0.0, 0
        print(f"=== {m['label']} ({m['slug']}) ===", flush=True)

        with out_path.open("a") as fh:
            for c in CONTROLS:
                if (c["name"], 0) in done:
                    continue
                fh.write(json.dumps({
                    "task_name": c["name"], "sample": 0, "config": fp,
                    "pos": c["pos"], "neg": c["neg"],
                    "model_requested": m["slug"], "provider_requested": m["provider"],
                    "status": "ok", "provider_resolved": "n/a (synthetic control)",
                    "model_resolved": "n/a", "content": c["pattern"],
                    "pattern": c["pattern"], "usage": {}, "cost_usd": 0.0,
                    "latency_s": 0.0, "generation_id": None,
                }) + "\n")

            for task in tasks:
                for sample in range(args.k):
                    if (task["name"], sample) in done:
                        continue
                    if grand + model_cost >= args.max_spend:
                        print(f"  ! spend cap ${args.max_spend:.2f} reached; stopping",
                              flush=True)
                        stopped = True
                        break
                    res = call(
                        model=m["slug"], provider=m["provider"],
                        prompt=build_prompt(task),
                        temperature=d["temperature"], max_tokens=d["max_tokens"],
                        reasoning=reasoning,
                    )
                    usage = res.usage or {}
                    ctd = usage.get("completion_tokens_details") or {}
                    fh.write(json.dumps({
                        "task_name": task["name"], "sample": sample, "config": fp,
                        "pos": task["pos"], "neg": task["neg"],
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
                        failures += 1
                        if failures <= 5:
                            print(f"  ! {task['name']}: {res.status} "
                                  f"{(res.error or '')[:80]}", flush=True)
                    time.sleep(0.15)
                if stopped:
                    break

        grand += model_cost
        print(f"  {wrote} call(s), {failures} failure(s), ${model_cost:.4f}   "
              f"(running total ${grand:.4f})\n", flush=True)

    print(f"TOTAL THIS RUN: ${grand:.4f}")
    if stopped:
        print("STOPPED EARLY at the spend cap. Re-run with a higher --max-spend "
              "to continue; completed rows are on disk and will be skipped.")


if __name__ == "__main__":
    main()

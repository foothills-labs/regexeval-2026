"""Re-attempt rows that failed for transport reasons, and rewrite them in place.

Anthropic's content filter fires stochastically on this corpus: a probe of 20
previously-rejected StructuredRegex descriptions, all of them benign ("A
string that starts with one or more digits and optionally ends with 'NU' or
'DG'"), succeeded on 8 when sent again unchanged. Left alone it cost
claude-opus-5 182 of 622 tasks, which would have been reported as a 29%
coverage hole caused by infrastructure rather than by the model.

Retrying is sound here only because the failure is independent of the answer:
the filter fires before there is an answer to judge, and the identical prompt
succeeds or fails on different attempts. This does not select for better
regexes. It would be unsound to retry a *refusal*, where the model has seen
the task and declined, so those are left alone.

Rewrites <model>.jsonl with recovered rows substituted for failed ones,
preserving row order and the configuration fingerprint. Residual failures stay
in the file and are reported by the scorer.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import call, extract_pattern  # noqa: E402

ROSTER = json.loads((Path(__file__).parent / "models.json").read_text())

# Transport-level failures: no answer was produced, so re-asking is not
# resampling. A refusal is not in this set.
RETRYABLE = ("content_filter", "http_error", "no_provider")


def retryable(row) -> bool:
    if row.get("status") == "ok" and row.get("pattern"):
        return False
    err = str(row.get("error") or "")
    return any(k in err or row.get("status") == k for k in RETRYABLE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="structuredregex")
    ap.add_argument("--model", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--max-spend", type=float, required=True)
    args = ap.parse_args()

    import csv
    prompts = {}
    with open(args.corpus) as fh:
        for i, r in enumerate(csv.DictReader(fh, delimiter="\t")):
            prompts[f'{r["problem_id"]}#{i}'] = r["description"].strip()

    models = ROSTER["models"] if isinstance(ROSTER, dict) else ROSTER
    m = next(x for x in models if x["label"] == args.model)

    path = config.PREDICTIONS_DIR / args.run / f"{args.model}.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    spent = 0.0
    recovered_total = 0
    for rnd in range(1, args.rounds + 1):
        targets = [i for i, r in enumerate(rows)
                   if not r["task_name"].startswith("control/") and retryable(r)]
        if not targets:
            print(f"round {rnd}: nothing left to retry")
            break
        recovered = 0
        for i in targets:
            if spent >= args.max_spend:
                print(f"  spend cap ${args.max_spend:.2f} reached")
                break
            name = rows[i]["task_name"]
            prompt = (prompts[name] + "\n\nReply with only the regular expression "
                      "pattern in a single fenced code block.")
            res = call(m["slug"], m["provider"], prompt, temperature=None,
                       max_tokens=400, reasoning={"enabled": False})
            spent += res.cost_usd or 0.0
            if res.ok and extract_pattern(res.content):
                old = rows[i]
                rows[i] = {
                    **old,
                    "status": res.status,
                    "provider_resolved": res.provider_resolved,
                    "model_resolved": res.model_resolved,
                    "content": res.content,
                    "pattern": extract_pattern(res.content),
                    "usage": res.usage or {},
                    "cost_usd": res.cost_usd,
                    "latency_s": round(res.latency_s, 2),
                    "generation_id": res.generation_id,
                    "error": None,
                    "recovered_on_retry": rnd,
                }
                recovered += 1
        recovered_total += recovered
        print(f"round {rnd}: {len(targets)} attempted, {recovered} recovered, "
              f"${spent:.4f} spent", flush=True)
        if spent >= args.max_spend:
            break

    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    left = sum(1 for r in rows
               if not r["task_name"].startswith("control/") and retryable(r))
    real = sum(1 for r in rows if not r["task_name"].startswith("control/"))
    print(f"\n{args.model}: recovered {recovered_total}, {left} still failing "
          f"of {real} tasks ({100*(real-left)/real:.1f}% coverage), ${spent:.4f}")


if __name__ == "__main__":
    main()

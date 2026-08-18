"""Are the tasks Anthropic's filter rejects unrepresentative?

claude-opus-5 lost 84 of 622 StructuredRegex tasks to a content filter that
five retry rounds could not clear, so its score rests on a subset that was
not chosen at random. If those 84 tasks are systematically harder or easier
than the rest, opus is not comparable to the other ten models and should not
be reported beside them.

The other ten models answered all 622. Comparing their pass rate on the 84
blocked tasks against their pass rate on the 538 opus kept measures the bias
directly, using data already collected. No API calls.
"""
from __future__ import annotations

import json
import math
import re
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def full_match(pattern, text):
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, 2)
    try:
        return re.fullmatch(pattern, text) is not None
    except (_Timeout, re.error, RecursionError, OverflowError):
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def passes(pattern, pos, neg):
    return (all(full_match(pattern, s) is True for s in pos)
            and all(full_match(pattern, s) is False for s in neg))


def load(label):
    path = config.PREDICTIONS_DIR / "structuredregex" / f"{label}.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return [r for r in rows if not r["task_name"].startswith("control/")]


def main():
    opus = load("claude-opus-5")
    blocked = {r["task_name"] for r in opus
               if r["status"] != "ok" or not r.get("pattern")}
    kept = {r["task_name"] for r in opus} - blocked
    print(f"opus blocked on {len(blocked)} tasks, answered {len(kept)}\n")

    labels = sorted(p.stem for p in
                    (config.PREDICTIONS_DIR / "structuredregex").glob("*.jsonl")
                    if p.stem != "claude-opus-5")

    hdr = f"{'model':26s} {'pass on blocked':>16s} {'pass on kept':>14s} {'diff':>8s}"
    print(hdr)
    print("-" * len(hdr))
    diffs = []
    for label in labels:
        b = k = bn = kn = 0
        for r in load(label):
            if r["status"] != "ok" or not r.get("pattern"):
                continue
            good = passes(r["pattern"], r["pos"], r["neg"])
            if r["task_name"] in blocked:
                bn += 1
                b += good
            else:
                kn += 1
                k += good
        pb, pk = 100 * b / bn, 100 * k / kn
        diffs.append(pb - pk)
        print(f"{label:26s} {pb:15.1f}% {pk:13.1f}% {pb-pk:+7.1f}")

    mean = sum(diffs) / len(diffs)
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1))
    print("-" * len(hdr))
    print(f"mean difference across the ten models: {mean:+.1f} points "
          f"(sd {sd:.1f}, n={len(diffs)})")
    print()
    if abs(mean) < 5:
        print("The blocked tasks are not markedly harder or easier. Reporting opus\n"
              "on its 538-task subset is defensible, with the coverage stated.")
    else:
        print("The blocked tasks differ materially from the rest. opus's subset is\n"
              "biased and its numbers should not be placed beside the other ten.")


if __name__ == "__main__":
    main()

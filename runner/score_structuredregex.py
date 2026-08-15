"""Score the StructuredRegex replication. Reference-independent only.

Two metrics, neither of which consults an answer key:

  pass@1        every positive string full-matches and no negative string does
  vulnerable@1  the regexbench safety screen flags the generated pattern

There is deliberately no dfa-eq and no exact match here. StructuredRegex's
own references are in a prefix DSL, and those are the reference-dependent
metrics this paper argues against trusting anyway. The point of this run is
to check whether the two trustworthy axes replicate off RegexEval.

Full-match semantics: StructuredRegex targets describe a whole string
(`concat(...)` from first character to last), and its positive examples are
whole strings. `re.fullmatch` is therefore the correct test, and a pattern
the model anchors itself scores identically either way.

Reads predictions/, writes results/structuredregex_scores.json. No API calls.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import signal
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

from regexbench.safety import screen  # noqa: E402

MATCH_TIMEOUT_S = 2


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def full_match(pattern: str, text: str):
    """None if the pattern cannot be compiled or blows up on this input."""
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, MATCH_TIMEOUT_S)
    try:
        return re.fullmatch(pattern, text) is not None
    except (_Timeout, re.error, RecursionError, OverflowError):
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def passes(pattern: str, pos, neg):
    for s in pos:
        if full_match(pattern, s) is not True:
            return False
    for s in neg:
        if full_match(pattern, s) is not False:
            return False
    return True


def is_vulnerable(pattern: str):
    try:
        return str(screen(pattern, empirical=True).risk) != "Risk.SAFE"
    except Exception:
        return None


def wilson(k, n):
    """95% interval; small cells here make the normal approximation unsafe."""
    if not n:
        return (0.0, 0.0)
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def score_model(path: Path):
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    controls = {}
    n = ok = passed = vuln = correct_secure = failed = 0

    for r in rows:
        pattern = r.get("pattern")
        name = r["task_name"]

        if name.startswith("control/"):
            if pattern:
                controls[name] = {
                    "passes": passes(pattern, r["pos"], r["neg"]),
                    "vulnerable": is_vulnerable(pattern),
                }
            continue

        n += 1
        if r["status"] != "ok" or not pattern:
            failed += 1
            continue
        ok += 1
        p = passes(pattern, r["pos"], r["neg"])
        v = is_vulnerable(pattern)
        passed += bool(p)
        vuln += bool(v)
        correct_secure += bool(p and v is False)

    return {
        "tasks": n, "answered": ok, "failed": failed,
        "pass_at_1": round(100 * passed / n, 1) if n else None,
        "pass_ci95": [round(x, 1) for x in wilson(passed, n)],
        "vulnerable_at_1": round(100 * vuln / ok, 1) if ok else None,
        "vuln_ci95": [round(x, 1) for x in wilson(vuln, ok)],
        "correct_and_secure_at_1": round(100 * correct_secure / n, 1) if n else None,
        "vuln_given_correct": round(100 * (passed - correct_secure) / passed, 1) if passed else None,
        "_counts": {"passed": passed, "vulnerable": vuln, "correct_secure": correct_secure},
        "controls": controls,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="structuredregex")
    args = ap.parse_args()

    pred_dir = config.PREDICTIONS_DIR / args.run
    out = {}
    bad_controls = []
    for path in sorted(pred_dir.glob("*.jsonl")):
        label = path.stem
        out[label] = score_model(path)
        c = out[label]["controls"]
        if c.get("control/good", {}).get("passes") is not True:
            bad_controls.append(f"{label}: control/good did not pass")
        if c.get("control/bad", {}).get("passes") is not False:
            bad_controls.append(f"{label}: control/bad did not fail")
        if c.get("control/vulnerable", {}).get("vulnerable") is not True:
            bad_controls.append(f"{label}: control/vulnerable was not flagged")

    hdr = f"{'model':26s} {'n':>5s} {'fail':>5s} {'pass@1':>8s} {'vuln@1':>8s} {'c&s@1':>8s} {'vuln|correct':>13s}"
    print(hdr)
    print("-" * len(hdr))
    for label, s in sorted(out.items(), key=lambda x: -(x[1]["correct_and_secure_at_1"] or 0)):
        print(f"{label:26s} {s['tasks']:5d} {s['failed']:5d} "
              f"{s['pass_at_1'] or 0:7.1f}% {s['vulnerable_at_1'] or 0:7.1f}% "
              f"{s['correct_and_secure_at_1'] or 0:7.1f}% "
              f"{s['vuln_given_correct'] or 0:12.1f}%")

    print()
    if bad_controls:
        print("CONTROL FAILURES -- do not trust these numbers:")
        for b in bad_controls:
            print("  " + b)
    else:
        print(f"controls passed for all {len(out)} models")

    dest = config.REPO / "results" / "structuredregex_scores.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()

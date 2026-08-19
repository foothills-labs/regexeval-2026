"""Why does the same screen find twice the vulnerability rate on the other corpus?

Section 4.5 offers three explanations for our correct-and-secure rate being
far above the joint-benchmark literature's, and section 4.6 finds the rate
itself doubles between our two corpora. Two of the three explanations are
about the *patterns*, not about the models, and they make opposite
predictions that structure can separate:

  attack surface     a regular expression has one failure mode and a backend
                     application has many, so the regex domain should look
                     safer whatever the corpus. Predicts nothing about the
                     gap between our two corpora.

  difficulty ceiling the correct subset is biased toward easy tasks whose
                     solutions have less room to backtrack. Predicts that
                     StructuredRegex's correct patterns are *simpler* than
                     Re(gEx|DoS)Eval's -- it is the easier corpus -- and so
                     should be *safer*, which is the opposite of what we see.

So the difficulty-ceiling story is testable here, and it is the one that
would deflate the finding. This measures the structural complexity of the
patterns models actually got right on each corpus: length, quantifier count,
group nesting depth, and how many quantifiers sit inside a group -- the last
being the shape that backtracks.

If StructuredRegex's correct patterns carry more repetition under more
nesting despite its tasks being twenty points easier, then the extra
vulnerability is coming from what the tasks ask for rather than from how hard
they are, and the difficulty-ceiling explanation does not survive.

No API calls. Reads committed predictions. Writes results/complexity_compare.json.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)

from regexbench.correctness import check  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402
from score_structuredregex import passes as sr_passes  # noqa: E402

QUANT = re.compile(r"[*+?]|\{\d+(?:,\d*)?\}")


def depth(pattern: str) -> int:
    """Deepest group nesting, ignoring escaped parentheses and classes."""
    best = current = 0
    in_class = escaped = False
    for ch in pattern:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "(":
            current += 1
            best = max(best, current)
        elif ch == ")":
            current = max(0, current - 1)
    return best


def quantified_groups(pattern: str) -> int:
    """Groups carrying a quantifier -- `(...)+`, `(...){2,}`.

    Counted because a quantifier applied to a group whose body can itself
    repeat is the canonical catastrophic-backtracking shape, and it is the
    structural difference a grammar over repetition would produce.
    """
    return len(re.findall(r"\)\s*(?:[*+?]|\{\d+(?:,\d*)?\})", pattern))


def features(pattern: str) -> dict:
    return {"length": len(pattern), "quantifiers": len(QUANT.findall(pattern)),
            "depth": depth(pattern), "quantified_groups": quantified_groups(pattern)}


def correct_patterns_regexeval(run: str) -> list[str]:
    """Every generated pattern that satisfied its task's tests.

    Correctness only, via `check` rather than `evaluate`: the equivalence
    engine is the expensive part of a full report and nothing here consults a
    reference.
    """
    by_name = {t.name: t for t in load_regexeval(str(config.require_dataset()))}
    out = []
    for path in sorted((config.PREDICTIONS_DIR / run).glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["task_name"].startswith("control/") or r["status"] != "ok" or not r.get("pattern"):
                continue
            pattern = normalize_pattern(r["pattern"])[0]
            try:
                if check(pattern, by_name[r["task_name"]]).accuracy == 1.0:
                    out.append(pattern)
            except Exception:
                continue
    return out


def correct_patterns_structuredregex() -> list[str]:
    """The same, on the common 513-task subset the replication reports.

    StructuredRegex predictions carry their own positive and negative strings,
    so correctness is recomputable without the corpus file -- and it is
    recomputed with that run's own scorer rather than a second implementation
    of the same rule.
    """
    directory = config.PREDICTIONS_DIR / "structuredregex"
    rows_by_model = {}
    for path in sorted(directory.glob("*.jsonl")):
        rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        rows_by_model[path.stem] = [r for r in rows if not r["task_name"].startswith("control/")]
    answered = [{r["task_name"] for r in rows
                 if r["status"] == "ok" and r.get("pattern")}
                for rows in rows_by_model.values()]
    common = set.intersection(*answered) if answered else set()

    out = []
    for rows in rows_by_model.values():
        for r in rows:
            if r["task_name"] not in common or r["status"] != "ok" or not r.get("pattern"):
                continue
            pattern = normalize_pattern(r["pattern"])[0]
            if sr_passes(pattern, r["pos"], r["neg"]):
                out.append(pattern)
    return out


def summarise(patterns: list[str]) -> dict:
    rows = [features(p) for p in patterns]
    out = {"n": len(rows)}
    for key in ("length", "quantifiers", "depth", "quantified_groups"):
        values = [r[key] for r in rows]
        out[key] = {"median": statistics.median(values),
                    "mean": round(statistics.mean(values), 2),
                    "p90": sorted(values)[int(0.9 * len(values))]}
    out["with_quantified_group_pct"] = round(
        100 * sum(1 for r in rows if r["quantified_groups"] > 0) / len(rows), 1)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    args = ap.parse_args()

    report = {
        "Re(gEx|DoS)Eval": summarise(correct_patterns_regexeval(args.run)),
        "StructuredRegex": summarise(correct_patterns_structuredregex()),
    }
    print(f"{'corpus':20s} {'n':>6s} {'len':>6s} {'quant':>6s} {'depth':>6s} "
          f"{'q-grp':>6s} {'has q-grp':>10s}")
    for name, b in report.items():
        print(f"{name:20s} {b['n']:6d} {b['length']['median']:6.0f} "
              f"{b['quantifiers']['median']:6.0f} {b['depth']['median']:6.0f} "
              f"{b['quantified_groups']['mean']:6.2f} "
              f"{b['with_quantified_group_pct']:9.1f}%")

    path = config.RESULTS_DIR / "complexity_compare.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())

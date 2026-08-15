"""Cross-corpus ReDoS screen: does the human-reference finding hold off RegexEval?

The main run measures ReDoS on one corpus. This screens gold and production
patterns from four independent sources with the identical regexbench safety
screen, to separate "benchmark answer keys are dangerous" from "people write
dangerous regexes".

No API calls. Costs nothing but CPU. Writes results/cross_corpus_redos.json.

Corpora
-------
RegexEval gold      human-written references from real user posts (the corpus
                    the main run scores against), all 762 rather than the 450
                    sampled for inference.
KB13                human-written references from Kushman & Barzilay (2013).
NL-RX-Synth         MACHINE-GENERATED from a grammar, then described by
                    crowdworkers. Included as a control, not as human data.
                    (NL-RX-Turk is excluded: its targ.txt is byte-identical to
                    NL-RX-Synth's. It is the same regexes with new prose.)
Production code     regexes extracted from shipped packages across eight
                    registries by Davis et al. (LinguaFranca, FSE 2019). This
                    is the population the "how do people write regexes" claim
                    is actually about.

Dialect note
------------
KB13 and NL-RX are written in the deep-regex DSL, where `&` is intersection
and `~` is negation. Python's `re` treats both as literal characters and
compiles them without complaint, so screening them raw silently measures the
wrong language. Those patterns are excluded rather than mistranslated.

Task-mix confound
-----------------
RegexEval is disproportionately validators (email, ISBN, hostname), which is
the shape that backtracks; production code is mostly small utility patterns.
The headline comparison is therefore repeated on the anchored `^...$` subset
of both, which is the closest matched population available.
"""
import json
import math
import random
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from regexbench.safety import screen

SC = Path("/tmp/claude-0/-home-user-regexleaderboard/"
          "4f381924-048f-55c1-baa3-50487ddcdad5/scratchpad")
SEED = 20260814
SAMPLE = 5000
ANCHORED_SAMPLE = 4000
WORKERS = 4

DSL = re.compile(r"[&~]")
ANCHORED = re.compile(r"^\^.*\$$")


def compiles(pattern):
    try:
        re.compile(pattern)
        return True
    except Exception:
        return False


def screen_one(pattern):
    try:
        return str(screen(pattern, empirical=True).risk)
    except Exception as exc:
        return "ERROR:" + type(exc).__name__


def rate(patterns):
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        verdicts = list(pool.map(screen_one, patterns, chunksize=16))
    counts = Counter(verdicts)
    errors = sum(v for k, v in counts.items() if k.startswith("ERROR"))
    n = len(patterns) - errors
    exp = counts.get("Risk.EXPONENTIAL", 0)
    poly = counts.get("Risk.POLYNOMIAL", 0)
    vuln = exp + poly
    p = vuln / n
    return {
        "n": n, "errors": errors, "exponential": exp, "polynomial": poly,
        "vulnerable": vuln, "rate_pct": round(100 * p, 1),
        "ci95_pct": round(100 * 1.96 * math.sqrt(p * (1 - p) / n), 1),
    }


def regexeval():
    data = json.loads((SC / "RegexEval.json").read_text())
    return list(dict.fromkeys(e["expression"] for e in data))


def deep_regex(name):
    path = SC / "deep-regex" / "datasets" / name / "targ.txt"
    uniq = list(dict.fromkeys(l.rstrip("\n") for l in path.open()))
    return [p for p in uniq if not DSL.search(p)]


def production():
    out = []
    path = SC / "lf" / "data" / "production-regexes" / "uniq-regexes-8.json"
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                pattern = json.loads(line).get("pattern")
            except Exception:
                continue
            if isinstance(pattern, str) and pattern and compiles(pattern):
                out.append(pattern)
    random.Random(SEED).shuffle(out)
    return out


def main():
    prod_all = production()
    corpora = [
        ("RegexEval gold (all 762)", "human, real user posts", regexeval()),
        ("KB13 (dialect-clean)", "human, Kushman & Barzilay 2013", deep_regex("KB13")),
        ("NL-RX-Synth (dialect-clean)", "MACHINE-GENERATED (control)", deep_regex("NL-RX-Synth")),
        (f"Production code (sample of {len(prod_all)})", "human, shipped packages", prod_all[:SAMPLE]),
    ]

    results = {"seed": SEED, "workers": WORKERS, "corpora": {}, "anchored": {}}
    print(f"seed {SEED}; regexbench safety screen, structural + empirical\n")
    for name, origin, pats in corpora:
        r = rate(pats)
        r["origin"] = origin
        results["corpora"][name] = r
        print(f"{name}\n   origin: {origin}")
        print(f"   screened {r['n']} ({r['errors']} errors); "
              f"exponential {r['exponential']}, polynomial {r['polynomial']}")
        print(f"   VULNERABLE {r['rate_pct']}% +/- {r['ci95_pct']}\n")

    ev_anchored = [p for p in regexeval() if ANCHORED.match(p)]
    prod_anchored = [p for p in prod_all if ANCHORED.match(p)][:ANCHORED_SAMPLE]
    print("=" * 68)
    print("Task-mix control: anchored ^...$ patterns only\n")
    for name, pats in (("RegexEval gold, anchored", ev_anchored),
                       ("Production code, anchored", prod_anchored)):
        r = rate(pats)
        results["anchored"][name] = r
        print(f"{name:34s} n={r['n']:5d}  vuln {r['rate_pct']:5.1f}% +/- {r['ci95_pct']}")

    print("\nmodels in the main run: 7.3%-10.7%, pooled 9.0%")

    out = Path(__file__).resolve().parent.parent / "results" / "cross_corpus_redos.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    sys.exit(main())

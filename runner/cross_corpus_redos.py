"""Cross-population ReDoS screen: does the human-reference finding hold off RegexEval?

The main run measures ReDoS on one corpus. This screens gold and production
patterns from five further sources with the identical regexbench safety
screen, to separate "benchmark answer keys are dangerous" from "people write
dangerous regexes".

No API calls. Costs nothing but CPU. Reads the artifacts `make setup-corpora`
pins and writes results/cross_corpus_redos.json.

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
Stack Overflow      regexes posted to Stack Overflow, from the same artifact.
                    This is the provenance Re(gEx|DoS)Eval draws from, so it
                    separates "answer keys are dangerous" from "forum
                    snippets are dangerous".
RegexLib            regexes published to regexlib.com for reuse. A library of
                    shared validators: written once, published, and never
                    subjected to traffic. The closest population in kind to a
                    benchmark answer key.

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
of every population, which is the closest matched set available. Model
outputs get the identical restriction in runner/anchored_models.py.

Screen validity
---------------
Three things could make the cross-population comparison an artifact of the
instrument rather than a fact about the populations, and each gets a number
here rather than a caveat:

1. **The compile filter is not uniform.** Every population is screened by
   CPython's `re`, and what will not compile is dropped. The production
   corpus is 5% Perl and Ruby syntax `re` rejects, concentrated in exactly
   the anchored validator shapes the matched comparison rests on. `drops`
   reports the rate per population and per registry; the `normalised`
   robustness run recovers what can be recovered (runner/dialect.py) and
   re-screens.
2. **Two registries cannot backtrack at all.** godoc targets RE2 and
   crates.io the Rust `regex` crate, both linear-time by construction, where
   catastrophic backtracking is impossible however the pattern is written.
   The `backtracking_only` robustness run drops them.
3. **A SAFE verdict is a screening outcome.** Sensitivity is measured
   separately, per population, in runner/screen_calibration.py.
"""
import json
import math
import random
import re
import warnings
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from dialect import is_anchored, to_python  # noqa: E402

# Screening a corpus means compiling tens of thousands of patterns people
# actually wrote, and CPython warns about constructs that are legal today and
# may not stay so -- `[[a-z]]`, `[a-z--0]`. The warning is about the pattern,
# not about us, and one per pattern buries the output. The patterns are
# screened as written either way.
warnings.filterwarnings("ignore", category=FutureWarning)

from regexbench.safety import screen  # noqa: E402

SEED = 20260814
SAMPLE = 5000
ANCHORED_SAMPLE = 4000
WORKERS = 4

DSL = re.compile(r"[&~]")
ANCHORED = re.compile(r"^\^.*\$$")

# Registries whose regexes run on a backtracking engine. RE2 (godoc) and the
# Rust regex crate (crates.io) are linear-time, so ReDoS is not a property
# their patterns can have.
LINEAR_ENGINE_REGISTRIES = {"godoc", "crates.io"}


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
    data = json.loads(config.require_dataset().read_text())
    return list(dict.fromkeys(e["expression"] for e in data))


def deep_regex(name):
    path = config.DEEP_REGEX_DIR / "datasets" / name / "targ.txt"
    raw = [line.rstrip("\n") for line in path.open()]
    uniq = list(dict.fromkeys(raw))
    clean = [p for p in uniq if not DSL.search(p)]
    return clean, {"raw": len(raw), "unique": len(uniq),
                   "dsl_excluded": len(uniq) - len(clean), "screened": len(clean)}


def production_pool():
    """Every production pattern, with the registries it was found in.

    Returned before the compile filter so the filter itself can be measured.
    """
    out = []
    path = config.LINGUA_FRANCA_DIR / "data" / "production-regexes" / "uniq-regexes-8.json"
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            pattern = obj.get("pattern")
            if isinstance(pattern, str) and pattern:
                registries = frozenset(obj.get("useCount_registry_to_nModules") or {})
                out.append((pattern, registries))
    return out


def internet_pool(source):
    """Stack Overflow / RegexLib patterns from the LinguaFranca artifact."""
    path = (config.LINGUA_FRANCA_DIR / "data" / "internet-regexes" / source / "data" /
            ("internetSources-stackoverflow.json" if source == "stackoverflow"
             else "internetSources-regExLib.json"))
    seen = []
    with path.open(errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            for pattern in obj.get("patterns", []):
                if isinstance(pattern, str) and pattern:
                    seen.append(pattern)
    return list(dict.fromkeys(seen))


def shuffled(items):
    items = list(items)
    random.Random(SEED).shuffle(items)
    return items


def drop_report(pool, label):
    """What the compile filter removes, and whether the removal is uniform."""
    kept = [p for p in pool if compiles(p)]
    return kept, {"population": label, "pool": len(pool), "compiled": len(kept),
                  "dropped": len(pool) - len(kept),
                  "dropped_pct": round(100 * (len(pool) - len(kept)) / len(pool), 1)}


def main():
    config.require_corpora()
    results = {"seed": SEED, "workers": WORKERS,
               "corpora": {}, "anchored": {}, "drops": {}, "robustness": {}}

    prod_pool = production_pool()
    so_pool = internet_pool("stackoverflow")
    lib_pool = internet_pool("regexlib")

    # --- the compile filter, measured before anything is screened ------------
    prod_patterns = [p for p, _ in prod_pool]
    for pool, label in ((prod_patterns, "Production code"),
                        (so_pool, "Stack Overflow"),
                        (lib_pool, "RegexLib")):
        _, rep = drop_report(pool, label)
        results["drops"][label] = rep
        print(f"compile filter | {label:16s} pool {rep['pool']:7d}  "
              f"dropped {rep['dropped']:6d} ({rep['dropped_pct']}%)")

    by_registry = Counter()
    dropped_by_registry = Counter()
    for pattern, registries in prod_pool:
        ok = compiles(pattern)
        for r in registries:
            by_registry[r] += 1
            if not ok:
                dropped_by_registry[r] += 1
    results["drops"]["by_registry"] = {
        r: {"patterns": by_registry[r], "dropped": dropped_by_registry[r],
            "dropped_pct": round(100 * dropped_by_registry[r] / by_registry[r], 1),
            "linear_engine": r in LINEAR_ENGINE_REGISTRIES}
        for r in sorted(by_registry)
    }
    print("\ncompile filter by registry (production):")
    for r, d in results["drops"]["by_registry"].items():
        note = "  [linear engine: ReDoS impossible]" if d["linear_engine"] else ""
        print(f"   {r:12s} {d['patterns']:7d} patterns, {d['dropped']:6d} dropped "
              f"({d['dropped_pct']}%){note}")

    # --- baseline: the six populations, unchanged ----------------------------
    prod_all = shuffled(p for p in prod_patterns if compiles(p))
    so_all = shuffled(p for p in so_pool if compiles(p))
    lib_all = shuffled(p for p in lib_pool if compiles(p))

    kb13, kb13_counts = deep_regex("KB13")
    nlrx, nlrx_counts = deep_regex("NL-RX-Synth")
    results["drops"]["KB13"] = kb13_counts
    results["drops"]["NL-RX-Synth"] = nlrx_counts

    corpora = [
        ("RegexEval gold (all 762)", "human, real user posts", regexeval()),
        ("KB13 (dialect-clean)", "human, Kushman & Barzilay 2013", kb13),
        ("NL-RX-Synth (dialect-clean)", "MACHINE-GENERATED (control)", nlrx),
        (f"RegexLib (all {len(lib_all)})", "human, published for reuse", lib_all),
        (f"Stack Overflow (sample of {len(so_all)})", "human, forum posts", so_all[:SAMPLE]),
        (f"Production code (sample of {len(prod_all)})", "human, shipped packages",
         prod_all[:SAMPLE]),
    ]

    print(f"\nseed {SEED}; regexbench safety screen, structural + empirical\n")
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
    so_anchored = [p for p in so_all if ANCHORED.match(p)][:ANCHORED_SAMPLE]
    lib_anchored = [p for p in lib_all if ANCHORED.match(p)][:ANCHORED_SAMPLE]
    print("=" * 68)
    print("Task-mix control: anchored ^...$ patterns only\n")
    for name, pats in (("RegexEval gold, anchored", ev_anchored),
                       ("RegexLib, anchored", lib_anchored),
                       ("Stack Overflow, anchored", so_anchored),
                       ("Production code, anchored", prod_anchored)):
        r = rate(pats)
        results["anchored"][name] = r
        print(f"{name:34s} n={r['n']:5d}  vuln {r['rate_pct']:5.1f}% +/- {r['ci95_pct']}")

    # --- robustness: does the instrument make the production number? ---------
    #
    # Normalisation is applied only to patterns that do not already compile,
    # so the normalised population is exactly the baseline plus whatever was
    # recovered. Applying it everywhere would also rewrite patterns `re`
    # already accepts, and the comparison would stop being nested.
    print("\n" + "=" * 68)
    print("Robustness: screen validity\n")

    def normalise(pattern):
        return pattern if compiles(pattern) else to_python(pattern)

    prod_norm_pool = [(normalise(p), regs) for p, regs in prod_pool]
    prod_norm_pool = [(p, regs) for p, regs in prod_norm_pool if p is not None]
    recovered = len(prod_norm_pool) - len(prod_all)
    print(f"dialect normalisation recovered {recovered} of "
          f"{results['drops']['Production code']['dropped']} dropped production patterns")

    variants = {
        "production, normalised": [p for p, _ in prod_norm_pool],
        "production, backtracking registries only":
            [p for p, regs in prod_pool
             if compiles(p) and (regs - LINEAR_ENGINE_REGISTRIES)],
        "production, normalised + backtracking only":
            [p for p, regs in prod_norm_pool if regs - LINEAR_ENGINE_REGISTRIES],
    }
    for label, pool in variants.items():
        pool = shuffled(pool)
        allr = rate(pool[:SAMPLE])
        anch = rate([p for p in pool if is_anchored(p)][:ANCHORED_SAMPLE])
        results["robustness"][label] = {"all": allr, "anchored": anch,
                                        "pool": len(pool)}
        print(f"{label:44s} pool {len(pool):6d}")
        print(f"{'':44s}   all      {allr['rate_pct']:5.1f}% +/- {allr['ci95_pct']} "
              f"(n={allr['n']})")
        print(f"{'':44s}   anchored {anch['rate_pct']:5.1f}% +/- {anch['ci95_pct']} "
              f"(n={anch['n']})")
    results["robustness"]["recovered_by_normalisation"] = recovered

    out = config.RESULTS_DIR / "cross_corpus_redos.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    sys.exit(main())

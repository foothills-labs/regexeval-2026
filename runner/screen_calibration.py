"""Is the ReDoS screen equally sensitive across the populations we compare?

The cross-population ordering only means something if the screen misses
vulnerable patterns at the same rate everywhere. Production patterns are
longer and structurally different from RegexLib showcase validators, so a
differential miss rate could generate the entire ordering without any of the
populations differing in the way we claim.

`vulnerable` being a lower bound is the right caveat for one population and
is not enough for six. This measures the miss rate per population.

Three verdicts per pattern
--------------------------
screen      regexbench's structural + empirical screen: the instrument under
            test. Covers three of the five families catalogued by Siddiq et
            al., so its misses are the question.

detector    weideman-RegexStaticAnalysis, from the artifact of Davis et al.
            (2019) -- the same detector their ecosystem study used. Wholly
            independent of regexbench: a different analysis (NFA ambiguity
            over EDA and IDA), a different language, a different author.
            EDA is exponential, IDA is polynomial.

dynamic     ground truth, and the reason this is a calibration rather than
            two opinions. When the detector calls a pattern vulnerable it
            emits an exploit string as (separators, pumps, suffix); we build
            the input at growing pump counts and *time CPython's own matcher*
            on it in a subprocess under a hard timeout. A confirmed blow-up is
            a fact about the engine the paper screens with, not a second
            static approximation.

What comes out
--------------
For each population: the screen's recall against dynamically confirmed
vulnerability, and its agreement with the detector. Recall is the number that
has to be stable across populations for the ordering to survive; the report
also stratifies by pattern length and by quantifier count, since those are
the covariates on which the populations most obviously differ.

Needs `make setup-corpora` and `make detector`. No API calls. CPU and JVM only.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import signal
import subprocess
import sys
import tempfile
import time
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import cross_corpus_redos as cc  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

# Screening a corpus means compiling tens of thousands of patterns people
# actually wrote, and CPython warns about constructs that are legal today and
# may not stay so -- `[[a-z]]`, `[a-z--0]`. The warning is about the pattern,
# not about us, and one per pattern buries the output. The patterns are
# screened as written either way.
warnings.filterwarnings("ignore", category=FutureWarning)

from regexbench.safety import screen  # noqa: E402

SEED = 20260819
PER_STRATUM = 120          # sampled per (population, screen verdict)
BATCH = 30                 # patterns per JVM launch
PATTERN_TIMEOUT = 5        # seconds the detector may spend on one pattern
DETECTOR_TIMEOUT = 400     # seconds per batch, as a backstop
PUMPS = (25, 50, 100, 200, 400, 800, 1600)
DYNAMIC_TIMEOUT = 1.0      # seconds per (pattern, input)
WORKERS = 4
# Above this input length a hang no longer distinguishes exponential from
# merely quadratic: 2,000 characters is 4 million steps for a quadratic
# matcher, which is already seconds.
EXPONENTIAL_LENGTH = 400
SLICE = 600                # candidates screened per round when filling a stratum

DETECTOR = (config.LINGUA_FRANCA_DIR / "analysis" / "performance" / "vuln-regex-detector" /
            "src" / "detect" / "src" / "detectors" / "weideman-RegexStaticAnalysis")

# Characters an ordinary pattern does not accept, appended so that `search` has
# to fail rather than succeed early. The detector's own suffix assumes the
# pattern is matched against the whole input; the screen uses search semantics,
# and under search a suffix that lets the match succeed measures nothing.
# Nothing is unmatched by every pattern -- `.` takes anything -- so this is a
# heuristic, and the fullmatch form is what covers the patterns it misses.
POISON = "￿!"

_BLOCK = re.compile(r'^\d+\. pattern = ".*"$')
_EXPLOIT = re.compile(r"(EDA|IDA) exploit string as JSON:\s+(\{.*\})")


def detector_verdicts(patterns: list[str]) -> dict[str, dict]:
    """Run the independent detector over a batch, one JVM for the batch.

    A batch that crashes or times out is retried one pattern at a time, so a
    single pathological input costs its own verdict and not the batch's.
    """
    if not patterns:
        return {}
    with tempfile.NamedTemporaryFile("w", suffix=".regex", delete=False) as fh:
        # The detector reads one pattern per line, so a pattern containing a
        # newline cannot be expressed. Those go in with the newline escaped
        # rather than being silently truncated at it.
        for p in patterns:
            fh.write(p.replace("\n", "\\n") + "\n")
        path = fh.name
    # The detector's own per-pattern timeout, rather than Davis's harness
    # setting `--timeout=0` and enforcing one itself. Without it a single
    # pathological pattern stalls its whole batch indefinitely, and the batch
    # then falls back to one JVM per pattern at the same cost each. A pattern
    # the analysis cannot finish in PATTERN_TIMEOUT is reported unanalysable,
    # which is a verdict this already handles.
    cmd = ["java", "-cp", f"{DETECTOR}/bin:{DETECTOR}/lib/gson-2.8.2.jar", "driver.Main",
           f"--if={path}", "--test-eda-exploit-string=false", "--ida=true",
           f"--timeout={PATTERN_TIMEOUT}", "--simple"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=DETECTOR_TIMEOUT).stdout
    except subprocess.TimeoutExpired:
        out = ""
    finally:
        Path(path).unlink(missing_ok=True)

    parsed = _parse_detector(out)
    if len(parsed) == len(patterns) or len(patterns) == 1:
        return {p: parsed.get(i + 1, {"verdict": "UNKNOWN", "exploits": []})
                for i, p in enumerate(patterns)}
    merged: dict[str, dict] = {}
    for p in patterns:
        merged.update(detector_verdicts([p]))
    return merged


def _parse_detector(out: str) -> dict[int, dict]:
    """Per-pattern verdicts out of the detector's numbered report."""
    verdicts: dict[int, dict] = {}
    index = None
    for line in out.splitlines():
        if _BLOCK.match(line.strip()):
            index = len(verdicts) + 1
            verdicts[index] = {"verdict": "SAFE", "exploits": []}
            continue
        if index is None:
            continue
        found = _EXPLOIT.search(line)
        if found:
            kind, blob = found.group(1), found.group(2)
            try:
                verdicts[index]["exploits"].append(json.loads(blob))
            except Exception:
                continue
            # EDA is the stronger claim and wins if both fire.
            if verdicts[index]["verdict"] != "EDA":
                verdicts[index]["verdict"] = kind
        elif "SKIPPED" in line:
            verdicts[index]["verdict"] = "SKIPPED"
        elif line.startswith("TIMEOUT in "):
            # The detector gave up on this pattern. Recording it as SAFE --
            # which is what defaulting the block would do -- would count the
            # patterns hardest to analyse as evidence that nothing is there,
            # and those are concentrated in exactly the long, deeply nested
            # patterns whose distribution differs between the populations
            # being compared. Unanalysable is its own verdict.
            verdicts[index]["verdict"] = "TIMEOUT"
    return verdicts


def attack_inputs(exploit: dict, pumps: int) -> list[tuple[str, str]]:
    """The detector's evil input at a given pump count, as (text, method).

    Two forms, because the two match methods fail differently: the detector's
    own suffix, matched whole; and a poisoned suffix, searched. A pattern only
    has to blow up under one of them to be vulnerable in practice.
    """
    separators = exploit.get("separators") or []
    pump_strings = exploit.get("pumps") or []
    if not pump_strings or len(separators) != len(pump_strings):
        return []
    core = "".join(s + p * pumps for s, p in zip(separators, pump_strings))
    return [(core + (exploit.get("suffix") or ""), "fullmatch"), (core + POISON, "search")]


# The probe reads its arguments as JSON on stdin rather than from argv.
# Patterns and attack inputs contain newlines and, occasionally, NUL, and argv
# carries neither -- passing them there raises before the pattern is ever run,
# which would silently score a pathological pattern as safe.
class _MatchTimeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise _MatchTimeout()


def _time_match(pattern: str, text: str, method: str, timeout: float):
    """Seconds CPython spends matching, or None if it did not finish.

    Timed in this process rather than in a child. CPython's matching engine
    checks for signals, so `setitimer` interrupts even a catastrophic match,
    and a per-probe subprocess costs more than the measurement: the ladder
    runs a dozen probes per pattern and process startup dominated everything.
    `process_time` rather than wall clock, so a loaded machine cannot
    manufacture a vulnerability.
    """
    try:
        compiled = re.compile(pattern)
    except Exception:
        return None
    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    start = time.process_time()
    try:
        getattr(compiled, method)(text)
        return time.process_time() - start
    except _MatchTimeout:
        return None
    except Exception:
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def blows_up(pattern: str, exploits: list[dict]) -> dict:
    """Does the detector's evil input actually blow up under CPython?

    Two ways to be confirmed, because the two complexity classes show
    themselves differently at input sizes we can run:

    * **Exponential.** Matching does not finish inside the timeout at a pump
      count small enough that a linear matcher would be instant. The hang is
      the evidence.
    * **Polynomial.** A quadratic matcher needs inputs in the hundreds of
      thousands of characters before it takes seconds, which is not practical
      over thousands of patterns. So instead of waiting for a hang we measure
      the growth: fit log(time) against log(input length) across the ladder
      and confirm when the slope is clearly above linear. `\\s*\\s*x` comes out
      near 2 in milliseconds, where waiting for it to time out would take
      minutes.

    The ladder stops as soon as it has an answer: a timeout settles it, and so
    does a pattern still running in microseconds at the largest input, which
    is not going to be super-linear at any size worth defending against.
    """
    floor = 1e-3
    best = {"confirmed": False, "kind": None, "slope": None, "trace": []}
    for exploit in exploits:
        trace = []
        for pumps in PUMPS:
            measured = []
            for text, method in attack_inputs(exploit, pumps):
                seconds = _time_match(pattern, text, method, DYNAMIC_TIMEOUT)
                if seconds is None:
                    # A timeout confirms the pattern; it does not by itself
                    # establish a degree. Calling every hang exponential is
                    # the threshold-for-measurement substitution this paper
                    # criticises in its own screen, so: a hang on an input a
                    # linear or even quadratic matcher would finish in
                    # microseconds is exponential, and a hang that needs a
                    # large input is super-linear of unestablished degree.
                    kind = ("exponential" if len(text) <= EXPONENTIAL_LENGTH
                            else "super-linear")
                    return {"confirmed": True, "kind": kind, "slope": None,
                            "pumps": pumps, "length": len(text), "method": method,
                            "trace": trace}
                trace.append([len(text), method, seconds])
                measured.append(seconds)
            # Still in the noise at the top of the ladder: nothing to fit.
            if pumps == PUMPS[-1] and max(measured, default=0) < floor:
                break
        for method in ("fullmatch", "search"):
            points = [(n, t) for n, m, t in trace if m == method and t > floor]
            slope = _loglog_slope(points)
            if slope is not None and slope > (best["slope"] or 0):
                best = {"confirmed": slope >= 1.5,
                        "kind": "polynomial" if slope >= 1.5 else None,
                        "slope": round(slope, 2), "method": method, "trace": trace}
        if not best["trace"]:
            best["trace"] = trace
    return best


def _loglog_slope(points):
    """Least-squares exponent of match time against input length.

    A linear matcher gives a slope near 1, quadratic near 2. Three points is
    the minimum that distinguishes a slope from a pair of measurements.
    """
    if len(points) < 3:
        return None
    xs = [math.log(n) for n, _ in points]
    ys = [math.log(t) for _, t in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denominator = sum((x - mx) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator


def _confirm(job):
    pattern, exploits = job
    return blows_up(pattern, exploits)


def quantifiers(pattern: str) -> int:
    return len(re.findall(r"[*+?]|\{\d+(?:,\d*)?\}", pattern))


def sample_populations() -> dict[str, list[str]]:
    """The six screened populations plus the model outputs."""
    prod_pool = cc.production_pool()
    pops = {
        "Re(gEx|DoS)Eval gold": cc.regexeval(),
        "KB13": cc.deep_regex("KB13")[0],
        "NL-RX-Synth": cc.deep_regex("NL-RX-Synth")[0],
        "RegexLib": [p for p in cc.internet_pool("regexlib") if cc.compiles(p)],
        "Stack Overflow": [p for p in cc.internet_pool("stackoverflow") if cc.compiles(p)],
        "Production code": [p for p, _ in prod_pool if cc.compiles(p)],
    }
    models: list[str] = []
    for path in sorted((config.PREDICTIONS_DIR / "sweep").glob("*.jsonl")):
        seen: set[str] = set()
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if (r["task_name"].startswith("control/") or r["status"] != "ok"
                    or not r.get("pattern") or r["task_name"] in seen):
                continue
            seen.add(r["task_name"])
            models.append(normalize_pattern(r["pattern"])[0])
    pops["Model outputs"] = models
    return pops


def _screen_bucket(pattern: str) -> str:
    try:
        return "SAFE" if screen(pattern, empirical=True).risk.name == "SAFE" else "VULNERABLE"
    except Exception:
        return "ERROR"


def stratified(patterns: list[str], rng) -> list[tuple[str, str]]:
    """Sample within each screen verdict, so both error directions are estimable.

    An unstratified draw from a population that screens at 5\% would spend the
    whole budget establishing specificity and almost none of it on recall,
    which is the quantity in question. Filling the vulnerable stratum from such
    a population means screening a few thousand candidates, so the screening
    runs in a pool and in slices: enough slices to fill the buckets, and no
    more.
    """
    unique = list(dict.fromkeys(patterns))
    rng.shuffle(unique)
    buckets: dict[str, list[str]] = defaultdict(list)
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for start in range(0, min(len(unique), 40 * PER_STRATUM), SLICE):
            chunk = unique[start:start + SLICE]
            for pattern, verdict in zip(chunk, pool.map(_screen_bucket, chunk, chunksize=16)):
                if verdict != "ERROR" and len(buckets[verdict]) < PER_STRATUM:
                    buckets[verdict].append(pattern)
            if all(len(buckets[k]) >= PER_STRATUM for k in ("SAFE", "VULNERABLE")):
                break
    return [(p, k) for k, ps in buckets.items() for p in ps]


def _band(value: int, key: str) -> str:
    edges = (20, 40, 80, 160) if key == "length" else (1, 2, 4, 8)
    for e in edges:
        if value <= e:
            return f"<={e}"
    return f">{edges[-1]}"


def _strata(confirmed: list[dict], key: str) -> dict:
    """Recall inside covariate bands, to see whether a miss is a miss anywhere.

    If the screen's recall falls with pattern length, and the populations
    differ in length, then part of the ordering is an artifact and the bands
    say how much.
    """
    total: Counter = Counter()
    caught: Counter = Counter()
    for r in confirmed:
        band = _band(r[key], key)
        total[band] += 1
        caught[band] += r["screen"] == "VULNERABLE"
    return {b: {"confirmed": total[b], "caught": caught[b],
                "recall_pct": round(100 * caught[b] / total[b], 1)}
            for b in sorted(total)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None, help="comma-separated population names")
    args = ap.parse_args()
    config.require_corpora()
    if not (DETECTOR / "bin").exists():
        raise SystemExit(f"Independent detector not built at {DETECTOR}\nRun:  make detector")

    rng = random.Random(SEED)
    report = {"seed": SEED, "per_stratum": PER_STRATUM, "populations": {}}
    wanted = {s.strip() for s in args.only.split(",")} if args.only else None

    for name, patterns in sample_populations().items():
        if wanted and name not in wanted:
            continue
        sample = stratified(patterns, rng)
        verdicts: dict[str, dict] = {}
        for i in range(0, len(sample), BATCH):
            verdicts.update(detector_verdicts([p for p, _ in sample[i:i + BATCH]]))

        jobs = [(p, verdicts.get(p, {}).get("exploits") or []) for p, _ in sample]
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            dynamics = list(pool.map(_confirm, jobs, chunksize=4))
        rows = []
        for (pattern, screen_verdict), dyn in zip(sample, dynamics):
            det = verdicts.get(pattern, {"verdict": "UNKNOWN", "exploits": []})
            rows.append({"screen": screen_verdict, "detector": det["verdict"],
                         "confirmed": bool(dyn and dyn["confirmed"]),
                         "length": len(pattern), "quantifiers": quantifiers(pattern)})

        confirmed = [r for r in rows if r["confirmed"]]
        caught = [r for r in confirmed if r["screen"] == "VULNERABLE"]
        agree = sum(1 for r in rows
                    if (r["screen"] == "VULNERABLE") == (r["detector"] in ("EDA", "IDA")))
        lengths = sorted(r["length"] for r in rows)
        quants = sorted(r["quantifiers"] for r in rows)
        block = {
            "sampled": len(rows),
            "screen_vulnerable": sum(1 for r in rows if r["screen"] == "VULNERABLE"),
            "detector_vulnerable": sum(1 for r in rows if r["detector"] in ("EDA", "IDA")),
            "detector_unanalysable": sum(1 for r in rows
                                         if r["detector"] in ("SKIPPED", "UNKNOWN", "TIMEOUT")),
            "dynamically_confirmed": len(confirmed),
            "confirmed_and_caught": len(caught),
            "recall_pct": round(100 * len(caught) / len(confirmed), 1) if confirmed else None,
            "agreement_pct": round(100 * agree / len(rows), 1) if rows else None,
            "median_length": lengths[len(lengths) // 2] if lengths else None,
            "median_quantifiers": quants[len(quants) // 2] if quants else None,
            "missed_by_length": _strata(confirmed, "length"),
            "missed_by_quantifiers": _strata(confirmed, "quantifiers"),
        }
        report["populations"][name] = block
        print(f"{name:24s} sampled {block['sampled']:4d}  confirmed {len(confirmed):4d}  "
              f"recall {block['recall_pct']}%  agreement {block['agreement_pct']}%  "
              f"median len {block['median_length']}", flush=True)

    recalls = [b["recall_pct"] for b in report["populations"].values()
               if b["recall_pct"] is not None]
    if recalls:
        report["recall_range_pct"] = [min(recalls), max(recalls)]
        print(f"\nrecall across populations: {min(recalls)}% to {max(recalls)}%")

    path = Path(args.out) if args.out else config.RESULTS_DIR / "screen_calibration.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())

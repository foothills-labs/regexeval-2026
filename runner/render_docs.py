"""Fill the tables in README.md and APPENDIX.md from committed results.

The paper's tables are generated (paper/make_tables.py) and the markdown
tables were not, which is how the two came to disagree: a reviewer found the
paper quoting one coverage figure and the docs another, and both quoting a
count that no longer reproduced. Same fix, same reason.

Each table lives between a pair of markers:

    <!-- generated: leaderboard -->
    ...anything here is replaced...
    <!-- /generated -->

Run via `make docs`. Reads only results/; no API access.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import config  # noqa: E402

SLUGS = {m["label"]: m["slug"] for m in
         json.loads((pathlib.Path(__file__).parent / "models.json").read_text())["models"]}


def scores(run: str) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(str(config.RESULTS_DIR / run / "*.json"))):
        if pathlib.Path(path).name in {
                "summary.json", "report.json", "disagreements.json",
                "undec_credit.json", "mcnemar_reference.json", "paired_intervals.json"}:
            continue
        d = json.loads(open(path).read())
        if isinstance(d, dict) and d.get("metrics"):
            rows.append(d)
    rows.sort(key=lambda d: -d["metrics"]["usable@3"])
    return rows


def leaderboard(rows) -> str:
    out = ["| Model | usable@3 | pass@3 | vulnerable@3 | tasks | failed | $/request |",
           "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for d in rows:
        m, label = d["metrics"], d["model"]
        out.append(
            f"| `{SLUGS.get(label, label)}` | **{m['usable@3']*100:.1f}%** | "
            f"{m['pass@3']*100:.1f}% | {m['vulnerable@3']*100:.1f}% | "
            f"{d.get('tasks_scored', '')} | {d['response_failures']}/{d['tasks_attempted']} | "
            f"${d['cost_usd_per_task']:.6f} |")
    return "\n".join(out)


def appendix(rows) -> str:
    out = ["| Model | dfa-eq@3 | dfa-eq@3 (decided) | exact@3 | undecidable | tasks | wrapped |",
           "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for d in sorted(rows, key=lambda d: -d["metrics"]["dfa-eq@3"]):
        m = d["metrics"]
        out.append(
            f"| `{d['model']}` | {m['dfa-eq@3']*100:.1f}% | "
            f"{m['dfa-eq@3 (decided)']*100:.1f}% | {m['exact@3']*100:.1f}% | "
            f"{m['undecided']} | {d.get('tasks_scored', '')} | {d['wrapped_responses']} |")
    return "\n".join(out)


def human_baseline() -> str:
    anch = json.loads((config.RESULTS_DIR / "anchored_models.json").read_text())
    mcn_path = config.RESULTS_DIR / "sweep" / "mcnemar_reference.json"
    mcn = json.loads(mcn_path.read_text())["models"] if mcn_path.exists() else {}
    ref = anch["reference"]["unrestricted"]
    out = ["| Source | n | vulnerable | exponential | polynomial | McNemar p |",
           "| --- | ---: | ---: | ---: | ---: | ---: |"]

    def row(label, b, p=None):
        n = b["n"]
        return (f"| {label} | {n} | {b['vulnerable']/n*100:.1f}% | "
                f"{b['exponential']/n*100:.1f}% | {b['polynomial']/n*100:.1f}% | "
                f"{'' if p is None else f'{p:.4f}'} |")

    out.append(row("**Human reference answers**", ref))
    for label in sorted(anch["models"],
                        key=lambda m: -anch["models"][m]["unrestricted"]["rate_pct"]):
        out.append(row(f"`{label}`", anch["models"][label]["unrestricted"],
                       (mcn.get(label) or {}).get("p_exact_two_sided")))
    out.append(row("**All models pooled**", anch["pooled"]["unrestricted"]))
    return "\n".join(out)


def populations() -> str:
    cc = json.loads((config.RESULTS_DIR / "cross_corpus_redos.json").read_text())
    anch = json.loads((config.RESULTS_DIR / "anchored_models.json").read_text())
    corpora = {k.split(" (")[0]: v for k, v in cc["corpora"].items()}
    out = ["| Population | written to be | n | vulnerable |", "| --- | --- | ---: | ---: |"]

    def row(label, written, b):
        return f"| {label} | {written} | {b['n']:,} | {b['rate_pct']:.1f}% ± {b['ci95_pct']:.1f} |"

    for label, written, key in (
            ("NL-RX-Synth (grammar-generated control)", "—", "NL-RX-Synth"),
            ("RegexLib, published for reuse", "read", "RegexLib"),
            ("KB13 gold answers", "read", "KB13"),
            ("Re(gEx\\|DoS)Eval gold answers", "read", "RegexEval gold"),
            ("Stack Overflow posts", "read", "Stack Overflow"),
            ("Production code", "run", "Production code")):
        out.append(row(label, written, corpora[key]))
    out.append("| | | | |")
    out.append("| **Anchored `^...$` only** | | | |")
    for label, written, key in (
            ("RegexLib, published for reuse", "read", "RegexLib, anchored"),
            ("Stack Overflow posts", "read", "Stack Overflow, anchored"),
            ("Re(gEx\\|DoS)Eval gold answers", "read", "RegexEval gold, anchored")):
        out.append(row(label, written, cc["anchored"][key]))
    out.append(row("**This work, 11 models pooled**", "—", anch["pooled"]["outputs"]))
    out.append(row("**Production code**", "**run**", cc["anchored"]["Production code, anchored"]))
    return "\n".join(out)


def splice(path: pathlib.Path, name: str, body: str, check: bool) -> bool:
    text = path.read_text()
    pattern = re.compile(
        r"(<!-- generated: " + re.escape(name) + r" -->\n).*?(\n<!-- /generated -->)",
        re.S)
    if not pattern.search(text):
        raise SystemExit(f"{path}: no marker block named '{name}'")
    updated = pattern.sub(lambda m: m.group(1) + body + m.group(2), text)
    if updated == text:
        return False
    if not check:
        path.write_text(updated)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--check", action="store_true",
                    help="fail if a rendered block differs from what is committed")
    args = ap.parse_args()

    rows = scores(args.run)
    repo = config.REPO if hasattr(config, "REPO") else pathlib.Path(".")
    blocks = [
        (repo / "README.md", "leaderboard", leaderboard(rows)),
        (repo / "README.md", "populations", populations()),
        (repo / "APPENDIX.md", "full-metrics", appendix(rows)),
        (repo / "APPENDIX.md", "human-baseline", human_baseline()),
    ]
    stale = [f"{p.name}:{name}" for p, name, body in blocks
             if splice(p, name, body, args.check)]
    if args.check:
        if stale:
            raise SystemExit("FAIL: generated doc blocks are stale: " + ", ".join(stale))
        print("OK: README.md and APPENDIX.md tables match the committed results.")
    else:
        print("rewrote " + (", ".join(stale) if stale else "nothing (already current)"))


if __name__ == "__main__":
    sys.exit(main())

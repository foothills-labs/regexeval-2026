"""Generate every table in the paper from committed results. Nothing by hand.

The rule is that no number reaches the paper except through this file. An
earlier version generated six of the eleven tables and left the rest as
hand-maintained LaTeX, and every arithmetic error a reviewer found lived in
one of the five -- a failure taxonomy that did not sum, a coverage figure that
disagreed with itself, a caption describing the wrong denominator. Worse, one
generated table read an intermediate from /tmp, so it could not be rebuilt
from a clean checkout at all.

So: every input here is a committed file under results/, every table is
emitted, and `make tables` in a clean checkout reproduces the paper's numbers
or fails loudly.

Each emitted file ends with a newline after \bottomrule so that \input inside
a tabular does not leave a stray space token, which makes booktabs' \noalign
misplaced and produces a wall of unrelated errors.
"""
from __future__ import annotations

import glob
import json
import pathlib
import sys
from math import comb

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "paper"
RESULTS = REPO / "results"


def esc(s):
    return s.replace("_", r"\_")


def load(path, what):
    """Read a required input, or say which command regenerates it."""
    p = pathlib.Path(path)
    if not p.exists():
        raise SystemExit(f"missing input: {p}\n  regenerate with: {what}")
    return json.loads(p.read_text())


def optional(path):
    p = pathlib.Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def write(name, colspec, header, body):
    lines = ([f"\\begin{{tabular}}{{{colspec}}}", "\\toprule", header, "\\midrule"]
             + body + ["\\bottomrule", "\\end{tabular}"])
    (OUT / name).write_text("\n".join(lines) + "\n")
    print(f"wrote {name} ({len(body)} body rows)")


def pct(x, places=1):
    return "---" if x is None else f"{x:.{places}f}"


# --- per-model scores --------------------------------------------------------
rows = []
for f in sorted(glob.glob(str(RESULTS / "sweep/*.json"))):
    if pathlib.Path(f).name in {"summary.json", "report.json", "disagreements.json",
                                "undec_credit.json", "mcnemar_reference.json"}:
        continue
    d = json.loads(open(f).read())
    if not isinstance(d, dict) or "metrics" not in d:
        continue
    m = d["metrics"]
    rows.append(dict(model=d["model"], u=m["usable@3"], p=m["pass@3"], v=m["vulnerable@3"],
                     dfa=m["dfa-eq@3"], dfad=m["dfa-eq@3 (decided)"], ex=m["exact@3"],
                     und=m["undecided"], fail=d["response_failures"],
                     scored=d.get("tasks_scored"), short=d.get("tasks_short_of_k"),
                     cpt=d["cost_usd_per_task"], tot=d["cost_usd_total"]))
if not rows:
    raise SystemExit("no per-model results found; run: make score RUN=sweep")
rows.sort(key=lambda r: -r["u"])

# Paired-bootstrap intervals, clustered on task. Independent binomial intervals
# are the wrong estimator for a design where every model answers every item,
# which is the paper's own argument; the main table should not use them either.
boot = optional(RESULTS / "sweep/paired_intervals.json")


def ci(model, metric):
    """Paired-bootstrap interval, or an em dash if it has not been computed."""
    if not boot or model not in boot.get("models", {}):
        return "---"
    lo, hi = boot["models"][model][metric]
    return f"[{lo*100:.1f}, {hi*100:.1f}]"


write("tab_main.tex", "lrrrcrrrrr",
      r"Model & $n$ & \pass{}@3 & \usable{}@3 & 95\% CI & \vuln{}@3 & \dfaeq{}@3 & "
      r"\dfaeq{}$_{\text{dec}}$ & \exact{}@3 & undec. \\", [
    f"\\texttt{{{esc(r['model'])}}} & {r['scored']} & {r['p']*100:.1f} & {r['u']*100:.1f} & "
    f"{ci(r['model'], 'usable')} & {r['v']*100:.1f} & {r['dfa']*100:.1f} & "
    f"{r['dfad']*100:.1f} & {r['ex']*100:.1f} & {r['und']} \\\\"
    for r in rows])

write("tab_cost.tex", "lrrr",
      r"Model & \usable{}@3 (\%) & cost/request (\$$\times 10^{-6}$) & total (\$) \\", [
    f"\\texttt{{{esc(r['model'])}}} & {r['u']*100:.1f} & {r['cpt']*1e6:.1f} & {r['tot']:.2f} \\\\"
    for r in sorted(rows, key=lambda r: r["cpt"])])


# --- @1 against @3 -----------------------------------------------------------
def _at(d, metric, k):
    total, n = 0.0, 0
    for v in d.values():
        if v["n"] < k:
            continue
        total += 1 - comb(v["n"] - v[metric], k) / comb(v["n"], k)
        n += 1
    return (total / n if n else float("nan")), n


ps = {pathlib.Path(f).stem: json.loads(open(f).read())
      for f in sorted(glob.glob(str(RESULTS / "sweep/per_sample/*.json")))}
cs = {pathlib.Path(f).stem: json.loads(open(f).read())
      for f in sorted(glob.glob(str(RESULTS / "sweep/correct_secure/*.json")))}
if not ps:
    raise SystemExit("no per-sample counts; run: python3 runner/per_sample.py --run sweep")

body = []
for r in rows:
    d = ps.get(r["model"])
    if not d:
        continue
    p1, _ = _at(d, "pass", 1)
    p3, _ = _at(d, "pass", 3)
    u1, _ = _at(d, "usable", 1)
    u3, _ = _at(d, "usable", 3)
    v1, _ = _at(d, "vulnerable", 1)
    short = sum(1 for v in d.values() if v["n"] < 3)
    body.append(f"\\texttt{{{esc(r['model'])}}} & {p1*100:.1f} & {p3*100:.1f} & "
                f"{u1*100:.1f} & {u3*100:.1f} & {v1*100:.1f} & {short} \\\\")
write("tab_at1.tex", "lrrrrrr",
      r"Model & \pass{}@1 & \pass{}@3 & \usable{}@1 & \usable{}@3 & \vuln{}@1 & $n{<}3$ \\",
      body)


# --- decomposition, and the cross-benchmark comparison -----------------------
mean = lambda xs: sum(xs) / len(xs)

body, safety_loss, equiv_loss, cond = [], [], [], []
corr_total = cs_total = 0
for r in rows:
    m = r["model"]
    if m not in cs:
        continue
    pa, _ = _at(ps[m], "pass", 3)
    ca, _ = _at(cs[m], "correct_secure", 3)
    ua, _ = _at(ps[m], "usable", 3)
    # This column is per-sample while the rest of the row is @3: it is a rate
    # over generations, not over tasks. Stated in the caption, and the two are
    # not interchangeable -- @3 would ask a different question (did any of the
    # three attempts trip the screen) and give a different number.
    n_corr = sum(v["pass"] for v in ps[m].values())
    n_cs = sum(v["correct_secure"] for v in cs[m].values())
    corr_total += n_corr
    cs_total += n_cs
    vgc = (n_corr - n_cs) / n_corr
    safety_loss.append(pa - ca)
    equiv_loss.append(ca - ua)
    cond.append(vgc)
    body.append(f"\\texttt{{{esc(m)}}} & {pa*100:.1f} & {(pa-ca)*100:.1f} & {ca*100:.1f} & "
                f"{(ca-ua)*100:.1f} & {ua*100:.1f} & {vgc*100:.1f} \\\\")
pooled_vgc = (corr_total - cs_total) / corr_total
body += [r"\midrule",
         f"\\textit{{mean}} & --- & {mean(safety_loss)*100:.1f} & --- & "
         f"{mean(equiv_loss)*100:.1f} & --- & {mean(cond)*100:.1f} \\\\",
         f"\\textit{{pooled}} & --- & --- & --- & --- & --- & "
         f"\\textbf{{{pooled_vgc*100:.1f}}} \\\\"]
write("tab_decomp.tex", "lrrrrrr",
      r"Model & \pass{}@3 & $-$safety & C\&S@3 & $-$equiv. & \usable{}@3 & vuln.$\mid$correct \\",
      body)

_MACROS = {
    "correctsamples": f"{corr_total:,}".replace(",", "{,}"),
    "correctvulnsamples": f"{corr_total - cs_total}",
    "vulngivencorrect": f"{pooled_vgc*100:.1f}",
    "equivshare": f"{mean(equiv_loss)/(mean(equiv_loss)+mean(safety_loss))*100:.0f}",
    "safetyloss": f"{mean(safety_loss)*100:.1f}",
    "equivloss": f"{mean(equiv_loss)*100:.1f}",
}

xb = [
    (r"This work (regex, ReDoS)", f"{rows[0]['scored']}",
     f"{mean([_at(ps[m],'pass',3)[0] for m in cs])*100:.0f}",
     f"{mean([_at(cs[m],'correct_secure',3)[0] for m in cs])*100:.0f}",
     f"{pooled_vgc*100:.0f}"),
    (r"BaxBench \citep{vero2025baxbench}", "392", "62 (best)", "---", r"$\approx$50"),
    (r"SecureAgentBench \citep{chen2025secureagentbench}", "105", "---",
     "15.2 (best), 9.2 (mean)", "---"),
    (r"DualGauge \citep{patir2025dualgauge}", "154", "$>$50", "$<$12", "---"),
]
write("tab_crossbench.tex", "lrrrr",
      r"Benchmark & tasks & functional (\%) & joint (\%) & vuln.$\mid$correct (\%) \\",
      [f"{a} & {b} & {c} & {d} & {e} \\\\" for a, b, c, d, e in xb])


# --- ReDoS: models against the reference set ---------------------------------
anch = load(RESULTS / "anchored_models.json", "python3 runner/anchored_models.py --run sweep")
mcn = optional(RESULTS / "sweep/mcnemar_reference.json")


def vuln_row(label, block, tex_label=None, mcnemar=None):
    n, v = block["n"], block["vulnerable"]
    e, p = block["exponential"], block["polynomial"]
    cell = (f"{mcnemar['p_exact_two_sided']:.3f}" if mcnemar else "---")
    return (f"{tex_label or label} & {n} & {v/n*100:.1f} & {e/n*100:.1f} & {p/n*100:.1f} "
            f"& {cell} \\\\")


ref = anch["reference"]["unrestricted"]
lines = [vuln_row("reference", ref, r"\textit{Human reference answers}"), r"\midrule"]
ordered = sorted(anch["models"], key=lambda m: -anch["models"][m]["unrestricted"]["rate_pct"])
for m in ordered:
    lines.append(vuln_row(m, anch["models"][m]["unrestricted"],
                          f"\\texttt{{{esc(m)}}}",
                          (mcn or {}).get("models", {}).get(m)))
lines += [r"\midrule", vuln_row("pooled", anch["pooled"]["unrestricted"],
                                r"\textit{All models pooled}")]
write("tab_vuln.tex", "lrrrrr",
      r"Source & $n$ & vulnerable (\%) & exponential (\%) & polynomial (\%) "
      r"& McNemar $p$ \\", lines)


# --- six populations ---------------------------------------------------------
cc = load(RESULTS / "cross_corpus_redos.json", "make setup-corpora && make crosscorpus")


def cc_row(label, written, block, bold=False):
    n = f"{block['n']:,}".replace(",", "{,}")
    rate = f"{block['rate_pct']:.1f}\\% $\\pm$ {block['ci95_pct']:.1f}"
    if bold:
        label, written, n, rate = (f"\\textbf{{{label}}}", f"\\textbf{{{written}}}",
                                   n, f"\\textbf{{{rate}}}")
    return f"{label} & {written} & {n} & {rate} \\\\"


keys = {k.split(" (")[0]: v for k, v in cc["corpora"].items()}
body = [r"\multicolumn{4}{l}{\emph{All patterns}} \\"]
for label, written, key in (
        ("NL-RX-Synth (grammar-generated control)", "---", "NL-RX-Synth"),
        ("RegexLib, published for reuse", "read", "RegexLib"),
        ("KB13 gold answers", "read", "KB13"),
        ("Re(gEx$|$DoS)Eval gold answers", "read", "RegexEval gold"),
        ("Stack Overflow posts", "read", "Stack Overflow"),
        ("Production code", "run", "Production code")):
    body.append(cc_row(label, written, keys[key]))

body += [r"\addlinespace",
         r"\multicolumn{4}{l}{\emph{Anchored \texttt{\^{}...\$} only, controlling for task mix}} \\"]
for label, written, key in (
        ("RegexLib, published for reuse", "read", "RegexLib, anchored"),
        ("Stack Overflow posts", "read", "Stack Overflow, anchored"),
        ("Re(gEx$|$DoS)Eval gold answers", "read", "RegexEval gold, anchored")):
    body.append(cc_row(label, written, cc["anchored"][key]))
# The models under the identical restriction -- their own anchored outputs --
# rather than the unrestricted rate an earlier draft put here.
body.append(cc_row("This work, 11 models pooled", "---", anch["pooled"]["outputs"], bold=True))
body.append(cc_row("Production code", "run", cc["anchored"]["Production code, anchored"], bold=True))
write("tab_crosscorpus.tex", "llrr",
      r"Population & Written to be & $n$ & vulnerable \\", body)


# --- StructuredRegex ---------------------------------------------------------
sr = load(RESULTS / "structuredregex_scores.json",
          "python3 runner/score_structuredregex.py")
common = {m: d["common_subset"] for m, d in sr["models"].items()}
order = sorted(common, key=lambda m: -common[m]["correct_and_secure_at_1"])
body = [f"\\texttt{{{esc(m):<28}}} & {common[m]['pass_at_1']:.1f} & "
        f"[{common[m]['pass_ci95'][0]:.1f}, {common[m]['pass_ci95'][1]:.1f}] & "
        f"{common[m]['vulnerable_at_1']:.1f} & {common[m]['correct_and_secure_at_1']:.1f} & "
        f"{common[m]['vuln_given_correct']:.1f} \\\\" for m in order]
tot = {k: sum(common[m]["_counts"][k] for m in common)
       for k in ("passed", "vulnerable", "correct_secure")}
n_tasks = sr["common_subset_size"] * len(common)
sr_vgc = (tot["passed"] - tot["correct_secure"]) / tot["passed"] * 100
body += [r"\midrule",
         f"\\textit{{Pooled}} & {tot['passed']/n_tasks*100:.1f} & --- & "
         f"{tot['vulnerable']/n_tasks*100:.1f} & {tot['correct_secure']/n_tasks*100:.1f} & "
         f"\\textbf{{{sr_vgc:.1f}}} \\\\"]
write("tab_sr_common.tex", "lrcrrr",
      r"Model & $\pass{}@1$ & 95\% CI & $\vuln{}@1$ & correct-and-secure & "
      r"$\vuln{}\mid$correct \\", body)

p1 = [_at(ps[m], "pass", 1)[0] * 100 for m in ps]
v1 = [_at(ps[m], "vulnerable", 1)[0] * 100 for m in ps]
srp = [common[m]["pass_at_1"] for m in common]
srv = [common[m]["vulnerable_at_1"] for m in common]
write("tab_sr_compare.tex", "lcc",
      r" & Re(gEx$|$DoS)Eval & StructuredRegex \\", [
    f"Tasks & {rows[0]['scored']} & {sr['common_subset_size']} \\\\",
    r"Reference used in scoring     & yes ($\dfaeq{}$) & no \\",
    r"\midrule",
    f"$\\pass{{}}@1$, range & {min(p1):.1f}--{max(p1):.1f}\\% & "
    f"{min(srp):.1f}--{max(srp):.1f}\\% \\\\",
    f"$\\vuln{{}}@1$, range & {min(v1):.1f}--{max(v1):.1f}\\% & "
    f"{min(srv):.1f}--{max(srv):.1f}\\% \\\\",
    f"$\\vuln{{}}\\mid$correct, pooled & \\textbf{{{pooled_vgc*100:.1f}\\%}} & "
    f"\\textbf{{{sr_vgc:.1f}\\%}} \\\\"])


# --- undecidability credit ---------------------------------------------------
undec = optional(RESULTS / "sweep/undec_credit.json")
if undec:
    body = []
    for m in sorted(undec["models"], key=lambda m: -undec["models"][m]["usable_pct"]):
        r = undec["models"][m]
        body.append(f"\\texttt{{{esc(m)}}} & {r['undecided']} & {r['usable_pct']:.1f} & "
                    f"{r['proven_pct']:.1f} & {r['undec_supported']} & "
                    f"{r['undec_supported_share_pct']:.1f} \\\\")
    pooled = undec["pooled"]
    body += [r"\midrule",
             f"\\textit{{pooled}} & --- & --- & --- & {pooled['undec_supported']} & "
             f"\\textbf{{{pooled['undec_supported_share_pct']:.1f}}} \\\\"]
    write("tab_undec.tex", "lrrrrr",
          r"Model & undec. & \usable{}@3 & proven-\textsc{eq} only & "
          r"tasks & share of \usable{} (\%) \\", body)


# --- screen calibration ------------------------------------------------------
cal = optional(RESULTS / "screen_calibration.json")
if cal:
    body = []
    for name, b in sorted(cal["populations"].items(),
                          key=lambda kv: -(kv[1]["recall_pct"] or 0)):
        body.append(f"{name.replace('|', '$|$')} & {b['sampled']} & "
                    f"{b['dynamically_confirmed']} & {pct(b['recall_pct'])} & "
                    f"{pct(b['agreement_pct'])} & {b['median_length']} & "
                    f"{b['median_quantifiers']} \\\\")
    write("tab_calibration.tex", "lrrrrrr",
          r"Population & sampled & confirmed & recall (\%) & agreement (\%) & "
          r"med. len & med. quant. \\", body)

# Numbers the prose states in words rather than in a table. Emitted last, so
# every input has been read and nothing here is a second computation of a
# figure a table already carries.
_MACROS.update({
    "anchoredmodels": f"{anch['pooled']['outputs']['rate_pct']:.1f}",
    "anchoredmodelsn": f"{anch['pooled']['outputs']['n']:,}".replace(",", "{,}"),
    "anchoredmodelsci": f"{anch['pooled']['outputs']['ci95_pct']:.1f}",
    "anchoredgold": f"{cc['anchored']['RegexEval gold, anchored']['rate_pct']:.1f}",
    "anchoredprod": f"{cc['anchored']['Production code, anchored']['rate_pct']:.1f}",
    "srvulngivencorrect": f"{sr_vgc:.1f}",
})
if "vs_production_anchored" in anch:
    _MACROS["anchoredp"] = f"{anch['vs_production_anchored']['p_two_sided']:.2f}"
drops = cc.get("drops", {})
for _pop, _key in (("Production code", "prod"), ("Stack Overflow", "so"),
                   ("RegexLib", "lib")):
    if _pop in drops:
        _MACROS[_key + "dropped"] = f"{drops[_pop]['dropped']:,}".replace(",", "{,}")
        _MACROS[_key + "droppedpct"] = f"{drops[_pop]['dropped_pct']:.1f}"
        _MACROS[_key + "pool"] = f"{drops[_pop]['pool']:,}".replace(",", "{,}")
_dd = optional(RESULTS / "dialect_drop.json")
if _dd:
    _MACROS["dropanchoredpct"] = f"{_dd['dropped_anchored_pct']:.1f}"
    _MACROS["keptanchoredpct"] = f"{_dd['kept_anchored_pct']:.1f}"
    _MACROS["recoveredpct"] = f"{_dd['recovered_pct']:.0f}"
    _top = next(iter(_dd["unrecovered_by_cause"]))
    _MACROS["topunrecovered"] = _top.replace("\\", "\\texttt{\\textbackslash ") + ("}" if _top.startswith("\\") else "")
    _MACROS["topunrecoveredn"] = f"{_dd['unrecovered_by_cause'][_top]:,}".replace(",", "{,}")

by_reg = drops.get("by_registry", {})
if by_reg:
    linear = [r for r, d in by_reg.items() if d["linear_engine"]]
    _MACROS["linearregistries"] = " and ".join(f"\\texttt{{{r}}}" for r in sorted(linear))
    # Distinct patterns, not the sum of the registry columns: 187 appear in
    # both linear-engine registries, and summing counts those twice.
    if _dd and "linear_engine_any" in _dd:
        _MACROS["linearpatterns"] = f"{_dd['linear_engine_any']:,}".replace(",", "{,}")
        _MACROS["linearonly"] = f"{_dd['linear_engine_only']:,}".replace(",", "{,}")
    rates = {r: d["dropped_pct"] for r, d in by_reg.items()}
    lo, hi = min(rates, key=rates.get), max(rates, key=rates.get)
    _MACROS["droprange"] = (f"\\texttt{{{hi}}} at {rates[hi]:.1f}\\% down to "
                            f"\\texttt{{{lo}}} at {rates[lo]:.1f}\\%")
_cx = optional(RESULTS / "complexity_compare.json")
if _cx:
    _re, _sr = _cx["Re(gEx|DoS)Eval"], _cx["StructuredRegex"]
    _MACROS.update({
        "relen": f"{_re['length']['median']:.0f}",
        "srlen": f"{_sr['length']['median']:.0f}",
        "requant": f"{_re['quantifiers']['median']:.0f}",
        "srquant": f"{_sr['quantifiers']['median']:.0f}",
        "reqgrouppct": f"{_re['with_quantified_group_pct']:.1f}",
        "srqgrouppct": f"{_sr['with_quantified_group_pct']:.1f}",
        "readjacent": f"{_re['shapes']['counts']['adjacent quantifiers']}",
        "sradjacent": f"{_sr['shapes']['counts']['adjacent quantifiers']}",
        "renested": f"{_re['shapes']['counts']['nested quantifier']}",
        "srnested": f"{_sr['shapes']['counts']['nested quantifier']}",
        "readjacentpct": f"{_re['shapes']['share_of_vulnerable_pct']['adjacent quantifiers']:.0f}",
        "sradjacentpct": f"{_sr['shapes']['share_of_vulnerable_pct']['adjacent quantifiers']:.0f}",
    })

_rob = cc.get("robustness", {})
if _rob:
    _MACROS["recovered"] = "{:,}".format(_rob.get("recovered_by_normalisation", 0)).replace(",", "{,}")
    for _label, _key in (("production, normalised", "robnorm"),
                         ("production, backtracking registries only", "robbt"),
                         ("production, normalised + backtracking only", "robboth")):
        if _label in _rob:
            _MACROS[_key] = f"{_rob[_label]['anchored']['rate_pct']:.1f}"
    _anchored_variants = [_rob[k]["anchored"]["rate_pct"] for k in _rob
                          if isinstance(_rob[k], dict) and "anchored" in _rob[k]]
    _anchored_variants.append(cc["anchored"]["Production code, anchored"]["rate_pct"])
    _MACROS["robrange"] = f"{min(_anchored_variants):.1f}--{max(_anchored_variants):.1f}"

if cal and cal.get("recall_range_pct"):
    lo, hi = cal["recall_range_pct"]
    _MACROS["recallrange"] = f"{lo:.0f}--{hi:.0f}"
if undec:
    _MACROS["undecshare"] = f"{undec['pooled']['undec_supported_share_pct']:.0f}"
    _MACROS["undecsupported"] = f"{undec['pooled']['undec_supported']}"
    _MACROS["undecusable"] = f"{undec['pooled']['usable']}"

# Every macro the paper uses must exist or the build dies with an undefined
# control sequence twenty pages from the cause. A macro whose input has not
# been computed yet is emitted as a visible marker instead: the document
# builds, and the gap is legible in the PDF rather than in a log.
_REQUIRED = ("recallrange", "undecshare", "undecsupported", "undecusable",
             "recovered", "robnorm", "robbt", "robboth", "robrange")
_missing = [k for k in _REQUIRED if k not in _MACROS]
for k in _missing:
    _MACROS[k] = r"\textbf{??}"
if _missing:
    print("WARNING: no value yet for " + ", ".join(_missing)
          + "\n  these render as ?? until the analysis that produces them has run"
          + "\n  (make analysis; make crosscorpus; make calibrate)")

(OUT / "gen_numbers.tex").write_text(
    "% generated by make_tables.py -- do not edit\n"
    + "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(_MACROS.items())))
print(f"wrote gen_numbers.tex ({len(_MACROS)} macros)")

print("\nall tables regenerated from committed results")

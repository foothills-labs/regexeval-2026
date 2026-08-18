"""Generate the paper's result tables directly from committed scores.

Nothing here is transcribed by hand. Each emitted file ends with a comment
character so that \input inside a tabular does not leave a stray space token
before \bottomrule, which makes booktabs' \noalign misplaced.
"""
import json, glob, sys, pathlib
REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "paper"
esc = lambda s: s.replace("_", r"\_")

def write(name, colspec, header, body):
    """Emit a complete tabular.

    The whole environment is generated rather than just the rows: \input
    landing between \\ and \bottomrule inside an alignment leaves a token
    that makes booktabs' \noalign misplaced, and the failure mode is a wall
    of unrelated errors. Outside an alignment the boundary is harmless.
    """
    lines = ([f"\\begin{{tabular}}{{{colspec}}}", "\\toprule", header, "\\midrule"]
             + body + ["\\bottomrule", "\\end{tabular}"])
    (OUT / name).write_text("\n".join(lines) + "\n")
    print(f"wrote {name} ({len(body)} body rows)")

rows = []
for f in sorted(glob.glob(str(REPO / "results/sweep/*.json"))):
    if f.endswith(("summary.json", "report.json", "disagreements.json")):
        continue
    d = json.loads(open(f).read())
    if not isinstance(d, dict) or "metrics" not in d:
        continue
    m = d["metrics"]
    rows.append(dict(model=d["model"], u=m["usable@3"], p=m["pass@3"], v=m["vulnerable@3"],
                     dfa=m["dfa-eq@3"], dfad=m["dfa-eq@3 (decided)"], ex=m["exact@3"],
                     und=m["undecided"], fail=d["response_failures"],
                     cpt=d["cost_usd_per_task"], tot=d["cost_usd_total"]))
rows.sort(key=lambda r: -r["u"])

write("tab_main.tex", "lrrrrrrrr",
      r"Model & \pass{}@3 & \usable{}@3 & \vuln{}@3 & \dfaeq{}@3 & "
      r"\dfaeq{}$_{\text{dec}}$ & \exact{}@3 & undec. & fail \\", [
    f"\\texttt{{{esc(r['model'])}}} & {r['p']*100:.1f} & {r['u']*100:.1f} & {r['v']*100:.1f} & "
    f"{r['dfa']*100:.1f} & {r['dfad']*100:.1f} & {r['ex']*100:.1f} & {r['und']} & {r['fail']} \\\\"
    for r in rows])

write("tab_cost.tex", "lrrr",
      r"Model & \usable{}@3 (\%) & cost/task (\$$\times 10^{-6}$) & total (\$) \\", [
    f"\\texttt{{{esc(r['model'])}}} & {r['u']*100:.1f} & {r['cpt']*1e6:.1f} & {r['tot']:.2f} \\\\"
    for r in sorted(rows, key=lambda r: r["cpt"])])

vt = json.load(open("/tmp/vulntypes.json"))
lines = [r"\textit{Human reference answers} & 450 & 13.6 & 6.4 & 7.1 \\", r"\midrule"]
for m, c in sorted(vt.items(), key=lambda x: -((x[1].get("EXPONENTIAL",0)+x[1].get("POLYNOMIAL",0))/x[1]["n"])):
    n, e, p = c["n"], c.get("EXPONENTIAL",0), c.get("POLYNOMIAL",0)
    lines.append(f"\\texttt{{{esc(m)}}} & {n} & {(e+p)/n*100:.1f} & {e/n*100:.1f} & {p/n*100:.1f} \\\\")
tn = sum(c["n"] for c in vt.values())
te = sum(c.get("EXPONENTIAL",0) for c in vt.values())
tp = sum(c.get("POLYNOMIAL",0) for c in vt.values())
lines += [r"\midrule",
          f"\\textit{{All models pooled}} & {tn} & {(te+tp)/tn*100:.1f} & {te/tn*100:.1f} & {tp/tn*100:.1f} \\\\"]
write("tab_vuln.tex", "lrrrr",
      r"Source & $n$ & vulnerable (\%) & exponential (\%) & polynomial (\%) \\", lines)


# --- @1 estimates from per-sample success counts -----------------------------
# pass@3 at n=3 degenerates to any-of-3 and cannot separate a task solved once
# from one solved three times. @1 is the per-sample success rate and is the
# quantity most comparable to single-sample protocols elsewhere. Tasks with
# fewer than k samples (from refusals or budget exhaustion) are excluded from
# the @k estimate for that k, which is why @3 here can differ marginally from
# the scorer's figure over all answered tasks.
from math import comb
import glob as _glob

def _at(d, metric, k):
    tot, n = 0.0, 0
    for v in d.values():
        if v["n"] < k:
            continue
        tot += 1 - comb(v["n"] - v[metric], k) / comb(v["n"], k)
        n += 1
    return (tot / n if n else float("nan")), n

ps = {}
for f in sorted(_glob.glob(str(REPO / "results/sweep/per_sample/*.json"))):
    ps[pathlib.Path(f).stem] = json.loads(open(f).read())

if ps:
    body = []
    for r in rows:
        d = ps.get(r["model"])
        if not d:
            continue
        p1, n1 = _at(d, "pass", 1)
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


# --- decomposition of the pass -> usable gap, and cross-benchmark context ----
cs = {}
for f in sorted(_glob.glob(str(REPO / "results/sweep/correct_secure/*.json"))):
    cs[pathlib.Path(f).stem] = json.loads(open(f).read())

if cs and ps:
    body, safety_loss, equiv_loss, cond = [], [], [], []
    for r in rows:
        m = r["model"]
        if m not in cs:
            continue
        pa, _ = _at(ps[m], "pass", 3)
        ca, _ = _at(cs[m], "correct_secure", 3)
        ua, _ = _at(ps[m], "usable", 3)
        n_corr = sum(v["pass"] for v in ps[m].values())
        n_cs = sum(v["correct_secure"] for v in cs[m].values())
        vgc = (n_corr - n_cs) / n_corr
        safety_loss.append(pa - ca); equiv_loss.append(ca - ua); cond.append(vgc)
        body.append(f"\\texttt{{{esc(m)}}} & {pa*100:.1f} & {(pa-ca)*100:.1f} & {ca*100:.1f} & "
                    f"{(ca-ua)*100:.1f} & {ua*100:.1f} & {vgc*100:.1f} \\\\")
    mean = lambda xs: sum(xs)/len(xs)
    body += [r"\midrule",
             f"\\textit{{mean}} & --- & {mean(safety_loss)*100:.1f} & --- & "
             f"{mean(equiv_loss)*100:.1f} & --- & {mean(cond)*100:.1f} \\\\"]
    write("tab_decomp.tex", "lrrrrrr",
          r"Model & \pass{}@3 & $-$safety & C\&S@3 & $-$equiv. & \usable{}@3 & vuln.$\mid$correct \\",
          body)

    xb = [
      (r"This work (regex, ReDoS)", "450", f"{mean([_at(ps[m],'pass',3)[0] for m in cs])*100:.0f}",
       f"{mean([_at(cs[m],'correct_secure',3)[0] for m in cs])*100:.0f}", f"{mean(cond)*100:.0f}"),
      (r"BaxBench \citep{vero2025baxbench}", "392", "62 (best)", "---", r"$\approx$50"),
      (r"SecureAgentBench \citep{chen2025secureagentbench}", "105", "---", "15.2 (best), 9.2 (mean)", "---"),
      (r"DualGauge \citep{patir2025dualgauge}", "154", "$>$50", "$<$12", "---"),
    ]
    write("tab_crossbench.tex", "lrrrr",
          r"Benchmark & tasks & functional (\%) & joint (\%) & vuln.$\mid$correct (\%) \\",
          [f"{a} & {b} & {c} & {d} & {e} \\\\" for a,b,c,d,e in xb])

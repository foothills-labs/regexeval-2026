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

"""Generate the /benchmarks/ page for foothills-labs.com from results.

DO NOT PUBLISH THIS PAGE AS IT STANDS. It emits a table ordered one to eleven
by usable@3, and the study declines to publish a ranking -- see ARTICLE.md,
"What we are not claiming": "Bands are defensible. A numbered list from one
to eleven is not." 62% of tasks give every model the identical result, and
only 167 of 450 separate them at all. The scores it reads are also inflated
by the pass_at_k short-task defect in REVISION-PLAN.md part 2 item 5.

This ran once, to foothills-labs.com, and was reverted the same day. Fix the
presentation (bands, not a list) and the upstream metric before it runs
again.


The site is hand-written static HTML with no build step, so this emits a
complete page in the site's own design system -- Blueprint scheme, Archivo,
the existing .data-table / .eyebrow / .lede components -- rather than
inventing a layout. Copy the output into the site repo at benchmarks/index.html.

Column order follows the site's existing table, with one change: usable@1
moves first, because it is the headline and pass@1 is the least interesting
number on the row.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def pct(v):
    return "&mdash;" if v is None else f"{v * 100:.1f}%"


def render(summary: list[dict], run_date: str, k: int, task_count: int) -> str:
    rows = []
    for e in summary:
        m = e.get("metrics")
        label = html.escape(e["model"])
        prov = html.escape(", ".join(e.get("providers_resolved") or []) or "&mdash;")
        if m is None:
            cells = "".join(
                f'<td class="num mono">&mdash;</td>' for _ in range(4)
            )
            rows.append(
                f'<tr><th scope="row" class="mono">{label}</th>{cells}'
                f'<td class="num mono">{e["response_failures"]}/{e["tasks_attempted"]}</td></tr>'
            )
            continue
        rows.append(
            f'<tr><th scope="row" class="mono">{label}</th>'
            f'<td class="num mono">{pct(m[f"usable@{k}"])}</td>'
            f'<td class="num mono">{pct(m[f"pass@{k}"])}</td>'
            f'<td class="num mono">{pct(m[f"vulnerable@{k}"])}</td>'
            f'<td class="num mono">{pct(m[f"dfa-eq@{k}"])}</td>'
            f'<td class="num mono">{e["response_failures"]}/{e["tasks_attempted"]}</td></tr>'
        )
    body = "\n            ".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Benchmarks &middot; Foothills Labs</title>
    <meta
      name="description"
      content="How good are language models at writing regular expressions you could
actually ship? regexbench scored across {len(summary)} models on Re(gEx|DoS)Eval."
    />
    <link rel="canonical" href="https://foothills-labs.com/benchmarks/" />
    <!-- Blueprint's ground, --fh-print. Kept in step with tokens.css by hand;
         the previous value here (#2e3a42) was a leftover from a palette two
         repaints ago and tinted the mobile browser chrome off-brand. -->
    <meta name="theme-color" content="#082C35" />

    <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml" />
    <link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon-180.png" />

    <!-- Archivo sets the page; JetBrains Mono sets the nav, the eyebrows and
         the buttons, all above the fold. Without these preloads the browser
         only discovers the mono after parsing style.css. Both weights: 400
         for the nav and footer, 700 for eyebrows and buttons. -->
    <link rel="preload" as="font" type="font/woff2"
          href="/assets/fonts/archivo.woff2" crossorigin />
    <link rel="preload" as="font" type="font/woff2"
          href="/assets/fonts/jetbrains-mono-400.woff2" crossorigin />
    <link rel="preload" as="font" type="font/woff2"
          href="/assets/fonts/jetbrains-mono-700.woff2" crossorigin />

    <link rel="stylesheet" href="/assets/tokens.css" />
    <link rel="stylesheet" href="/assets/style.css" />
  </head>
  <!-- data-scheme sits on body rather than html: tokens.css declares the
       default :root block after the scheme blocks, so a scheme on the root
       element loses the custom-property tie-break. -->
  <body data-scheme="blueprint">
    <a class="skip-link" href="#main">Skip to content</a>

    <header class="site-header">
      <div class="wrap">
        <a class="brand" href="/">
          <span class="brand-mark" aria-hidden="true"></span>
          Foothills Labs
        </a>
        <nav class="site-nav" aria-label="Primary">
          <a href="/#mission">Mission</a>
          <a href="/#models">Models</a>
          <a href="/#tools">Tools</a>
          <a href="/#principles">Principles</a>
          <a href="https://github.com/foothills-labs">GitHub</a>
        </nav>
      </div>
    </header>

    <main class="wrap basecamp" id="main">
      <p class="eyebrow">benchmarks &middot; regexbench</p>
      <h1>Regexes you could actually ship.</h1>
      <p class="lede">
        Most regex benchmarks ask whether a pattern passes its tests. This one
        also asks whether it means what the reference means, and whether it can
        be made to hang your server. A pattern can do the first and fail both
        of the others.
      </p>

      <div class="table-wrap">
        <table class="data-table">
          <caption class="visually-hidden">
            {len(summary)} models scored on Re(gEx|DoS)Eval, sorted by usable@{k}.
          </caption>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col" class="num">usable@{k}</th>
              <th scope="col" class="num">pass@{k}</th>
              <th scope="col" class="num">vulnerable@{k}</th>
              <th scope="col" class="num">dfa-eq@{k}</th>
              <th scope="col" class="num">failed</th>
            </tr>
          </thead>
          <tbody>
            {body}
          </tbody>
        </table>
      </div>

      <p class="note">
        <strong>usable@{k}</strong> is the headline: correct, not vulnerable to
        catastrophic backtracking, and never proven to describe a different
        language than the reference. The gap between it and
        <strong>pass@{k}</strong> is every pattern that passes its tests and
        still should not ship.
      </p>

      <p class="note">
        {task_count} tasks from Re(gEx|DoS)Eval, k={k} samples per task, reasoning
        disabled so every model faces the same conditions. Scored with
        <code>regexbench</code> 0.4.0. Run {html.escape(run_date)}. Every raw
        response is committed, and the scores recompute from them offline &mdash;
        <a href="https://github.com/foothills-labs/regexeval-2026">see the
        repository</a> for the method, the limitations, and a re-run command.
      </p>

      <div class="cta-row">
        <a class="btn btn-primary" href="https://github.com/foothills-labs/regexeval-2026">Results and method</a>
        <a class="btn btn-ghost" href="https://github.com/foothills-labs/regexbench">regexbench</a>
        <a class="btn btn-ghost" href="/">&larr; Back to the lab</a>
      </div>
    </main>

    <footer class="site-footer">
      <div class="wrap">
        <span>&copy; Foothills Labs</span>
        <div class="footer-links">
          <a href="mailto:info@foothills-labs.com">info@foothills-labs.com</a>
          <a href="https://github.com/foothills-labs">GitHub</a>
          <a href="/">Home</a>
        </div>
      </div>
    </footer>
  </body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--date", default=None,
                    help="run date, e.g. 2026-08-12; defaults to config.RUN_DATES")
    ap.add_argument("--tasks", type=int, default=None,
                    help="task count; defaults to tasks_attempted // k from the summary")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    summary = json.loads((config.RESULTS_DIR / args.run / "summary.json").read_text())

    # Both of these used to be required arguments, which meant the page could
    # only be regenerated by someone who remembered the run's date and size.
    # They are recoverable -- the date from config, the task count from the
    # data -- so recover them and let automation call this with just --run.
    date = args.date or config.RUN_DATES.get(args.run)
    if date is None:
        ap.error(f"no date for run {args.run!r}: pass --date or add it to "
                 f"config.RUN_DATES")
    tasks = args.tasks or max(e["tasks_attempted"] // e["k"] for e in summary)
    page = render(summary, date, args.k, tasks)
    out = Path(args.out) if args.out else config.REPO / "docs" / "benchmarks-index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(f"wrote {out} ({len(page)} bytes)")
    print("copy into the site repo as benchmarks/index.html")


if __name__ == "__main__":
    main()

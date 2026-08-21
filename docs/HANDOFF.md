# Handoff — regex leaderboard

> **Historical document.** Written when the lab traded as Foothills Labs;
> the org is now `plicara` and the lab is Plicara Labs (renamed 2026-08-20,
> before anything citable shipped). Foothills-era naming rules below are
> obsolete. Kept as the record of the handoff, not as guidance.

Context for an agent starting a **new repository** in the `plicara`
GitHub org. Written 2026-08-02. No prior context assumed.

**Working name:** `regexbench-results` (or `regex-leaderboard` — see §9).

---

## 1. What you are building

A **public benchmark run**: score a dozen or more LLMs on natural-language →
regex generation, and publish the numbers.

The scoring engine already exists and is published — `regexbench` on PyPI. You
are **not** rebuilding it. This repo:

1. Sends tasks to models through **OpenRouter**
2. Collects their regex predictions
3. Feeds those predictions to `regexbench` for scoring
4. Publishes results, methodology, and a re-run command

```
tasks ──> OpenRouter ──> predictions.jsonl ──> regexbench run ──> results
         (this repo)                          (pip install)      (this repo)
```

**Why a separate repo:** `regexbench` is a published PyPI package with a
stable-ish API. Results are data with a different cadence — they change every
time a model ships, and they must never be able to break the package's build.
Keeping them apart also means the leaderboard cites the tool as a dependency,
which is the honest relationship.

### Why this matters to the lab

Foothills' three-year plan puts "evaluate models rigorously — leaderboard others
cite" at rung **L0** of its capability ladder, and Gate A asks whether the
leaderboard is cited by someone who isn't us. Right now there is a measuring
instrument that has never publicly measured anything. **This repo produces the
lab's first artifact with a number in it.** Everything downstream — the regex
fine-tune, then anything above it — needs these baselines to beat.

## 2. `regexbench` — the dependency

`pip install regexbench` (v0.2.0). MIT-adjacent: **Apache-2.0**. Source:
`github.com/plicara/regexbench`. Read its README and CHANGELOG first.

### What it measures

Three axes, which is the point of it:

- **Correctness** — does the pattern match the positive examples and reject the
  negatives? Full-match or search semantics, per task.
- **Semantic equivalence** — is the generated pattern the *same language* as the
  reference? Done by compiling both to DFAs and comparing, which is the DFA-EQ
  metric from the literature. Exact string match is the wrong metric: `[0-9]+`
  and `[0-9][0-9]*` are the same language and different strings.
- **ReDoS safety** — can the pattern be made to hang? Structural analysis plus
  an empirical pass against attack strings.

### The API you need

```python
from regexbench import run                      # batch scoring
from regexbench.datasets import (
    load_regexeval,     # Re(gEx|DoS)Eval
    load_deep_regex,    # KB13 and both NL-RX corpora
    load_tasks,         # your own task file
)
```

Metrics produced: `pass@k`, `dfa-eq@k`, `exact@k`, `vulnerable@k`, `usable@k`,
plus `dfa-eq@k (decided)` over the analyzable subset. The `pass@k` estimator is
the unbiased one from Chen et al. (2021).

CLI: `regexbench run` with `--use-reference`, `--workers`, `--limit`, `--k`,
`--json`. It takes a tasks source and a **predictions file** — which is exactly
the seam this repo plugs into.

### `usable@k` is the headline

`usable` means **correct AND not ReDoS-vulnerable**. A pattern that passes every
test but can hang a server is not usable, and `Report.usable` returns `False`
for it.

Nobody else reports this axis. Lead with it. A model that scores 85% on
correctness and 60% on usable is a much more interesting finding than either
number alone, and it is the reason this leaderboard is worth publishing rather
than being the tenth regex eval.

### Known limitations — state these in the methodology

- **Python 3.10–3.13 only.** CPython 3.14 changed `\B` to match the empty string
  ([gh-124130](https://github.com/python/cpython/issues/124130)); the engine
  models the older behaviour and 13 of its own differential tests fail on 3.14.
  Pin your runner to ≤3.13.
- **Equivalence is decidable only on the regular subset.** Backreferences return
  `UNDECIDABLE`; lookaround and some syntax return `UNSUPPORTED`. That is why
  `dfa-eq@k (decided)` exists as a separate number — **report both**, and say
  what fraction was decidable. A `dfa-eq` score over only the easy subset,
  presented as the whole, is the kind of quiet inflation this lab exists to
  avoid.
- **Shorthand classes are Unicode-aware.** `\d` is not `[0-9]` — `\d` matches
  every Unicode digit. This is the change most likely to move a score versus
  other published regex evals, and it must be in the methodology or your numbers
  will look wrong to anyone comparing.
- **ReDoS `SAFE` is a screening result, not a proof.** Say so.

## 3. OpenRouter — and the trap that would invalidate everything

One API key, one OpenAI-compatible endpoint, hundreds of models. Ideal for this.
But there is a reproducibility hazard that must be handled **before** the first
run, not after.

### The trap

**By default, OpenRouter load-balances your request across multiple providers,
weighted by inverse square of price.** The same model slug can be served by
different companies, on different hardware, **at different quantizations**.

Quantization is the hidden quality variable — two providers can serve the same
weights at different precision and produce different outputs. There is a
LessWrong post titled, precisely,
["Not Pinning Your OpenRouter Provider Might Invalidate Your Evals"](https://www.lesswrong.com/posts/KsyoSAyBRXtwzSugg/not-pinning-your-openrouter-provider-might-invalidate-your).

**An unpinned benchmark measures the router, not the model.** Re-running it next
week can produce different numbers with no code change and no model change,
and you would have no way to tell.

### The fix — pin everything, record everything

```json
{
  "model": "<vendor>/<model>",
  "provider": {
    "order": ["<provider-slug>"],
    "allow_fallbacks": false,
    "quantizations": ["fp8"]
  }
}
```

- `provider.order` — providers to try, in order
- `provider.allow_fallbacks: false` — **fail rather than silently substitute.**
  A failed request you can see beats a substituted one you can't.
- `provider.quantizations` — filter to a precision
- `provider.only: ["provider/quant"]` — a hard endpoint pin
- `provider.require_parameters` — only providers supporting all your params

Other available fields: `sort`, `ignore`, `data_collection`, `max_price`,
`preferred_max_latency`, `preferred_min_throughput`, `zdr`.

**Record the resolved provider and quantization with every single response**, not
just the request config. The pin is an instruction; the response is evidence.
A result row without its provider is not reproducible and should not be
published.

### Cost and usage

Usage accounting returns token counts and **cost per request directly in the
response** — no extra call. Cached-token counts included. The `/generation`
endpoint retrieves usage asynchronously by generation ID for auditing.

**Log cost per request into the results.** A leaderboard that reports
`usable@k` alongside cost-per-task is substantially more useful than one
reporting quality alone, and you get it for free.

### Rate limits

- Free models: **20 req/min, 200 req/day** — usable for smoke tests, not a full
  sweep.
- Paid with $10+ credits: no OpenRouter platform limit, but **upstream provider
  throttling still applies**.
- A 429 returns immediately. **There is no queue, no auto-retry, no backoff.**
  The caller handles pacing and exponential backoff — build that into the
  runner from the start, because discovering it halfway through a paid sweep is
  expensive.

## 4. What to build

```
<repo>/
  runner/           OpenRouter client: pinning, retry, cost logging
  tasks/            the task set (or loaders for public corpora)
  predictions/      raw model output, committed — this is the evidence
  results/          scores, tables, the published artifact
  METHODOLOGY.md    how it was run, so someone else can re-run it
  README.md         the leaderboard itself
```

### Phase 1 — one model, end to end

Prove the pipeline on a single model and ten tasks before spending real money.
Verify the resolved provider and quantization appear in your logs. Verify
`regexbench run` scores the predictions file you produced.

### Phase 2 — the sweep

A dozen-plus models across frontier and open-weights. **Multiple samples per
task** — `pass@k` and `dfa-eq@k` are `@k` metrics and need `k` samples to mean
anything. Decide and record `k`, temperature, and max tokens.

### Phase 3 — publish

README with the table, `METHODOLOGY.md`, committed predictions, and a re-run
command. Include the negative results and anything surprising.

## 5. Methodology rules

These are the house style, and they are the reason to publish this at all.

1. **Pin provider and quantization; record what actually served each request.**
2. **Commit the raw predictions.** They are the evidence. Scores without them
   are an assertion.
3. **Report `dfa-eq@k` and `dfa-eq@k (decided)` together**, with the decidable
   fraction stated.
4. **Report cost per task** alongside quality.
5. **Run controls.** For a benchmark of *generated* output the control is a
   known-good and a known-bad prediction pushed through the whole pipeline —
   this catches a scorer silently returning zeros, which looks exactly like a
   model that failed.
6. **Publish failures.** Models that error, refuse, or return prose instead of a
   pattern are a finding, not missing data. Do not quietly drop them; report a
   response-parse-failure rate.
7. **Date every table and pin every model version.** "GPT-5" in August is not
   "GPT-5" in November.

## 6. Two failure modes to design against

Both have already bitten work in this lab:

- **A blocked or rate-limited request returning a plausible-looking body**,
  scored as if it were a real answer. A 429 body or an error page is not a
  prediction. Validate the response shape before scoring, and run the controls
  from rule 5 in every sweep.
- **A number that looks fine and is measuring nothing.** The 3.14 `\B` bug in
  `regexbench` was caught only because CI ran a version nobody expected to work.
  Assume your first sweep is wrong somewhere and look for it deliberately.

## 7. Prior art to position against

- **Re(gEx|DoS)Eval** — correctness plus ReDoS. The closest existing work;
  `regexbench` ships a loader for it.
- **KB13, NL-RX** — the classic NL→regex corpora. Old and noisy;
  `regexbench` found them only partially analyzable before word-boundary
  support landed.
- **RegexPSPACE** — equivalence and minimization as an LLM reasoning benchmark.

Read at least the Re(gEx|DoS)Eval paper before finalising methodology, so the
numbers are comparable to something.

## 8. Cost expectation

Unknown and worth estimating before spending. A dozen models × a few hundred
tasks × `k` samples is the shape. **Price it with a 10-task dry run first** and
extrapolate — the three-year plan's guidance is that inference spend is the
right place to put money and founder-hours are the scarce resource, so do not
optimise the sweep to save a few dollars.

## 9. Naming

Foothills convention: mountain names are reserved for **model releases** (the
Seven Summits); tools and artifacts get plain descriptive names — `labloop`,
`regexbench`. Follow that.

`regexbench-results` says exactly what it is and sorts next to the package.
`regex-leaderboard` is punchier if this is meant to be cited. Either is fine;
pick one and don't rename it later — a leaderboard's URL is its identity.

Hard rule for any Foothills naming: **always plural.** "Foothill Ventures" is an
existing VC firm.

## 10. Open questions

1. **Which task set?** Public corpora (KB13 / NL-RX / Re(gEx|DoS)Eval) make the
   numbers comparable to prior work. A fresh hand-written set avoids
   contamination — these corpora are old enough to be in every training set,
   which means high scores may measure memorisation. **Consider both: public for
   comparability, a small private set for the contamination check.** The gap
   between them is itself a publishable finding.
2. **Which `k`?** Costs scale linearly with it.
3. **Which models?** Frontier plus open-weights; the open-weights numbers are
   the ones that matter for the planned fine-tune baseline.
4. **Does OpenRouter's `seed` parameter work per-provider?** Unverified.
   Determinism would help but do not assume it.

## 11. Provenance

- `regexbench` capabilities: from its CHANGELOG and README, written by its
  author. Verified published on PyPI at 0.2.0.
- OpenRouter routing defaults, the `provider` field schema, usage accounting and
  rate limits: from OpenRouter's own documentation and blog, cross-checked
  against community write-ups.
- **`seed` behaviour is unverified** — the provider-routing docs do not cover it.
- Cost figures: none given here on purpose. Measure them (§8).

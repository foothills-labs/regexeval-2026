# Methodology

How the numbers in `README.md` were produced, and every judgement call that
could move them. Written against the **preview** run of 2026-08-11; the
same document will carry the full sweep, with this section updated rather
than replaced.

## Versions pinned

| Component | Pin |
| --- | --- |
| `regexbench` | 0.4.0, commit `05d7547b1a71e6dd5cb00d71bf4dac7732be3ecd` |
| Python | 3.11.15 |
| Dataset | Re(gEx|DoS)Eval, `RegexEval.json` from `s2e-lab/RegexEval@master` |

`regexbench` 0.4.0 is **not on PyPI** at time of writing (PyPI's latest is
0.3.0), so the pin is a git commit, not a version string. `pip install
regexbench==0.4.0` does not resolve. This matters more than usual because
0.4.0 changed scoring behaviour relative to 0.3.0 — see "Engine limits".

## Sampling

- `k = 1`, temperature **0.0**, `max_tokens = 200` for the preview.
- The full sweep will use `k = 5` — `pass@k` and `dfa-eq@k` are `@k`
  metrics and a single sample makes the `@k` notation meaningless. `k=1` in
  the preview is a cost decision for a pipeline test, not a methodology
  choice, and the preview table is labelled `@1` accordingly.
- `regexbench` uses the unbiased `pass@k` estimator from Chen et al.
  (2021), so numbers line up with published work.

## Prompt

One system message fixing the output contract, one user message carrying
the task's natural-language description verbatim from the corpus:

> **system:** You translate a natural-language description into a single
> Python `re`-compatible regular expression. Reply with ONLY the pattern in
> one fenced code block, no explanation.
>
> **user:** `{task.prompt}`\n\nReply with only the regular expression
> pattern in a single fenced code block.

No few-shot examples, no chain-of-thought instruction, no retry-on-bad-format.
Prompt engineering would improve every score and make them incomparable
to other published work; the prompt is deliberately plain and identical
across models.

## Extraction — and why two scores are reported

Models were asked for a fenced code block. The **strict** rule is: take the
last fenced block if any fence exists, else the whole trimmed reply.

Models do not reliably comply. In the preview, 6 of 30 successful responses
wrapped the pattern in host-language quoting — Python raw strings
(`r'\d+$'`), inline backticks, and JS-style `/pattern/flags`. Scored
literally, `r'\d+$'` is a pattern matching an `r`, a quote, and so on: it
fails, and it fails for a reason that has nothing to do with the model's
regex ability.

So every model is scored **twice from the same committed responses**:

- **strict** — the pattern exactly as emitted.
- **normalized** — with one layer of host-language quoting stripped
  (`r'…'`, `'…'`, `"…"`, `` `…` ``, `/…/flags`), up to 3 nested times.

Both appear in `results/`, along with `wrapped_responses` (how many were
normalized) and `wrapped_detail` (the before/after of each strip), so the
normalized number is auditable line by line against the raw response.

**Why not just pick one.** Strict alone reports a real capability
difference (instruction-following) as though it were a regex difference,
and it penalizes small models hardest — Llama-3.1-8b moves 0% → 20% on
`pass@1` from this rule alone. Normalized alone hides a genuine failure to
follow the output contract. Reporting one silently would be a choice with a
20-point effect that no reader could see. The README leads with normalized
and flags every value that differs.

## Provider pinning

Every request pins the provider and refuses substitution:

```json
{
  "provider": {
    "order": ["DeepInfra"],
    "allow_fallbacks": false,
    "quantizations": ["fp8"],
    "require_parameters": true
  }
}
```

By default OpenRouter load-balances across providers weighted by inverse
square of price, and providers may serve the same weights at different
quantizations on different engines. An unpinned benchmark measures the
router, not the model, and can produce different numbers next week with no
code change ([LessWrong: *Not Pinning Your OpenRouter Provider Might
Invalidate Your Research*](https://www.lesswrong.com/posts/KsyoSAyBRXtwzSugg/not-pinning-your-openrouter-provider-might-invalidate-your)).

- `allow_fallbacks: false` means a pinned provider that is down produces a
  **visible error**, not a silent reroute. This fired in the preview:
  `mistral-small-3.2` failed all 10 requests with upstream 429
  (`engine_overloaded`) from DeepInfra rather than being quietly served by
  Parasail at bf16. That is the intended outcome.
- `require_parameters: true` keeps routing to providers that honour the
  sampling parameters, rather than silently ignoring `temperature`.
- **The pin is the instruction; the response is the evidence.** The
  provider OpenRouter reports as having actually served each request is
  recorded per response and surfaced in `results/*.providers_resolved`. A
  response with no resolved provider is treated as a failed request and is
  never scored.

`seed` is **not** used. Its per-provider behaviour is unverified and
community reports say it does not guarantee reproducibility across
backends; temperature 0.0 is used instead, and runs are treated as
non-deterministic.

## Failure handling

Rule: **a failure is a finding, not missing data.**

- Responses are classified `ok` / `http_error` / `parse_failure` /
  `no_provider`. Only `ok` responses with a non-empty extracted pattern are
  scored.
- Everything else is counted in `response_failures` and itemized with its
  error in `failure_detail`, and the model stays in the table with its
  failure rate shown rather than being dropped.
- 429 and 5xx are retried with exponential backoff (2s, 4s, 8s, 16s, 32s).
  A 429 body is never treated as a prediction — this is the specific
  failure mode where an error page gets scored as if it were an answer.
- Exhausting retries is recorded as a failure for that task, not a zero
  that looks like a wrong answer. `mistral-small` therefore shows `—` in
  every metric column and `10/10` under response failures, not `0.0%`.

## Controls

Three synthetic predictions ride through the identical scoring path in
every model's run, because a scorer returning zeros looks exactly like a
model that failed:

| Control | Pattern | Must produce |
| --- | --- | --- |
| `control/good` | the task's own reference | `pass@1 = 1.0`, `usable@1 = 1.0` |
| `control/bad` | `z{5}` | `pass@1 = 0.0`, `usable@1 = 0.0` |
| `control/vulnerable` | `(a+)+b` | `vulnerable@1 = 1.0` |

`controls_all_as_expected` is asserted per model in `results/`. A sweep
whose controls do not come back exactly this way is discarded, not
published.

The known-bad control is deliberately a **regular** wrong pattern. An
earlier design used `(?!x)x`, which lands in the undecidable bucket and
reports `dfa-eq (decided)` as `n/a` rather than `0%` — so it would not have
exercised the decided-subset path at all.

## Engine limits — what regexbench can and cannot decide

These are properties of the scorer and must be read with the numbers:

- **Semantic equivalence is decidable only on the regular subset.**
  Backreferences make a pattern non-regular and return `UNDECIDABLE`.
  `dfa-eq@k` counts those as failures (a lower bound that cannot flatter);
  `dfa-eq@k (decided)` drops them from the denominator (the model alone).
  **Both are reported**, with the undecided count stated. In the preview,
  2–4 of 10 tasks per model were undecidable — a large fraction, and one
  reason the 10-task numbers should not be over-read.
- **Lookaround is decidable as of 0.4.0.** It returned `UNSUPPORTED` in
  0.3.0 and earlier. This raises the decided denominator relative to any
  previously published `regexbench` figure, so preview numbers are **not**
  comparable to 0.3.0 numbers.
- **Shorthand classes are Unicode-aware.** `\d` is not `[0-9]` — it matches
  every Unicode digit, because that is what Python's `re` does and
  `regexbench` runs the real `re`. This is the single change most likely to
  move a score relative to other published regex evals.
- **ReDoS `SAFE` is a screening result, not a proof.** It means no known-bad
  structural shape and no blow-up on the attack strings tried. The
  structural pass models three of the five vulnerability families in the
  ICPC 2024 study of LLM-generated regexes; the other two are caught only
  if the empirical pass happens to trip them. `vulnerable@k` is therefore a
  **lower bound** on real vulnerability.
- **Match semantics.** Re(gEx|DoS)Eval is loaded with the semantics its own
  loader sets (search). Its references pass 100% of their own tests under
  search and 94.0% under fullmatch — choosing wrong would score 46 gold
  patterns as failing tests they were written for. Verified in this
  environment with `--use-reference`: 762/762 references score `pass@1`
  99.9%, `dfa-eq@1` 100%.

## Known gaps in the preview

Stated because the preview is being published as a preview, not because
they are acceptable in the full run:

1. **10 tasks is not a ranking.** ±~30pp confidence interval on `pass@1`.
   The model ordering in the preview table should not be cited.
2. **`k=1`** — no `@k` signal at all.
3. **One corpus.** No KB13, and no private contamination-check set. The
   public corpora are old enough to be in training data, so a high score
   may measure memorisation; the planned private set exists to size that
   gap.
4. **`mistral-small` has no numbers** — a provider outage, not a model
   result. It should be re-run before any comparative claim.
5. **No `crosscheck()` pass yet.** 0.4.0 ships string-by-string differential
   verification against `re`; the full run should use it on controls as an
   independent check that the equivalence engine agrees with the engine
   that runs the correctness half.

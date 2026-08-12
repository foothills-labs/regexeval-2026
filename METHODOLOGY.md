# Methodology

Written as the questions a skeptical reader would ask, in the order they'd
ask them. The harder metrics and the engine's limits are in
[APPENDIX.md](APPENDIX.md).

Describes the **preview** run of 2026-08-11. The full run will update this
document rather than replace it.

---

### What exactly does a model see?

One instruction and one task description. Nothing else — no examples, no
"think step by step", no retry when the format is wrong.

> **system:** You translate a natural-language description into a single
> Python `re`-compatible regular expression. Reply with ONLY the pattern in
> one fenced code block, no explanation.
>
> **user:** *{the task's description, verbatim from the corpus}*
>
> Reply with only the regular expression pattern in a single fenced code block.

The prompt is deliberately plain. Tuning it would raise every score and
make the numbers incomparable to other published work. It is identical for
every model.

### What are the tasks?

**Re(gEx|DoS)Eval** — 762 regex problems collected from real users, each
with a description, strings that must match, strings that must not, and a
human-written reference answer. It's the closest existing benchmark to this
one, which makes our numbers comparable to prior work.

We don't redistribute it; `make setup` downloads it from
[s2e-lab/RegexEval](https://github.com/s2e-lab/RegexEval).

**The preview used 10 of those 762 tasks**, chosen by spreading evenly
across the corpus (indices 0, 75, 150, … 700) rather than taking the first
ten, which are all easy. Ten tasks is a pipeline test, not a measurement.

### How many samples per task?

The preview used **one** (`k=1`), at temperature 0.0. The full run will use
**five** (`k=5`).

This matters because models are non-deterministic: ask twice, get two
answers. A single sample measures luck as much as skill. `usable@5` asks
"if the model got five attempts, would at least one be shippable?" — which
is both a fairer question and the one a developer actually cares about.

The preview's `k=1` is a cost decision for a pipeline test. Every preview
number is labelled `@1` so it can't be mistaken for the real thing.

### Why is reasoning switched off?

Because leaving it on would compare different things to each other.

Of the eleven models on the board, **four do not reason at all** — Claude
Opus 5 and Sonnet 5, GPT-5.6 Sol and Terra returned zero reasoning tokens.
The other seven produce a hidden chain of thought before answering, billed
as output. Scoring them side by side with reasoning enabled would measure
"model plus thinking budget" against "model", and the leaderboard would
mostly be ranking who was allowed to think.

So every request sets `reasoning: {enabled: false}`, and this is recorded
with every response.

**It is also the difference between a $12 sweep and a $71 one.** Measured
on the corpus's *easiest* task ("match exactly one digit"):

| Model | reasoning tokens | cost per call |
| --- | ---: | ---: |
| `qwen3.6-max-preview` | 1,571 | $0.0098 |
| `gemini-3.6-flash` | 427 | $0.0033 |
| `glm-5.2` | 194 | $0.0006 |
| `claude-opus-5` | 0 | $0.0015 |

Qwen spent 1,571 tokens of hidden reasoning deciding how to match a single
digit, then answered `^[0-9]$`. With reasoning disabled it answered
`^[0-9]$` again, in 10 tokens, for **1/100th of the price**.

Two things this turned up that are worth stating plainly:

- **`reasoning: {effort: "low"}` is not a cheaper setting.** On
  `qwen3.6-max-preview` it produced *2,375* reasoning tokens — more than
  the default, at a higher price. Only `enabled: false` reliably reduces
  it.
- **A reasoning model with too small a token budget returns nothing at
  all.** At `max_tokens: 200`, three models produced empty content: the
  budget went entirely on hidden reasoning with nothing left to answer
  with. An empty completion is treated as a failed request, never as an
  empty pattern, because scoring it would look exactly like a model that
  answered badly.

Whether thinking actually helps at this task is a separate question, and a
more interesting one, so it is measured rather than assumed: a **thinking
slice** re-runs the reasoning-capable models on a subset with reasoning
enabled. That comparison is reported on its own, never mixed into the main
table.

### How is the pattern pulled out of the reply?

Take the last fenced code block if there is one; otherwise the whole
trimmed reply. Then strip one layer of host-language quoting — see
[the wrapper rule](APPENDIX.md#the-wrapper-rule), which changed one model's
score by 20 points and is therefore documented in the open rather than
buried in the code.

### How do you stop a rate-limit error being scored as a wrong answer?

By never letting a non-answer reach the scorer. Every response is
classified before scoring:

| Status | Meaning | Scored? |
| --- | --- | --- |
| `ok` | a real completion with a pattern in it | yes |
| `http_error` | error response, including 429 after retries | no — counted as a failure |
| `parse_failure` | a 200 with no usable content | no — counted as a failure |
| `no_provider` | no provider reported as having served it | no — counted as a failure |

429s and 5xx are retried with exponential backoff (2s, 4s, 8s, 16s, 32s).
If retries run out, that's recorded as a **failure**, not as a zero — the
distinction matters, because a zero looks like a wrong answer and a failure
looks like what it is. `mistral-small-3.2` shows `—` in every metric column
and `10/10` under failures for exactly this reason.

### How do you know the scorer itself works?

Three synthetic answers ride through the identical scoring path in every
run:

| Control | Submitted | Must produce |
| --- | --- | --- |
| `control/good` | the task's own reference | passes, usable |
| `control/bad` | `z{5}` | fails everything |
| `control/vulnerable` | `(a+)+b` | flagged vulnerable |

If any control misbehaves the run is discarded, not published — `make
score` exits non-zero. This catches the failure mode where a scorer
silently returns zeros, which is indistinguishable from a model that failed
unless you plant a known-good answer and check it comes back good.

The known-bad control is deliberately a *simple* wrong pattern. An earlier
version used `(?!x)x`, which lands in the undecidable bucket and so never
exercised the scoring path it was meant to test.

### Why pin the provider, and what does that actually do?

By default, OpenRouter routes each request to whichever provider is
cheapest at that moment, weighted by price. The same model can be served by
different companies, on different hardware, **at different numerical
precisions** — and lower precision can change the output.

So an unpinned benchmark measures the router, not the model. Re-run it next
week and the numbers move, with no code change and no way to tell why.
([Background reading.](https://www.lesswrong.com/posts/KsyoSAyBRXtwzSugg/not-pinning-your-openrouter-provider-might-invalidate-your))

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

- `allow_fallbacks: false` — if the pinned provider is down, **fail
  visibly** rather than quietly serve from somewhere else. This fired in
  the preview and cost us a model's worth of data. That is the correct
  trade: a failure you can see beats a substitution you can't.
- `require_parameters: true` — only route to providers that honour the
  sampling settings instead of ignoring them.
- **The pin is the instruction; the response is the evidence.** Which
  provider actually served each request is recorded per response and
  published in `results/*/providers_resolved`. A response that doesn't say
  who served it is discarded.

We do **not** use the `seed` parameter. Its behaviour differs by provider
and is not a reliable route to reproducibility, so runs are treated as
non-deterministic and the honesty comes from `k` samples instead.

### How is cost measured?

OpenRouter returns the cost of each request in the response itself, so
it's recorded per response and summed — not estimated from a price list.
Measured: about 105 prompt and 36 completion tokens per task.

### What's pinned, so this can be re-run in a year?

| Component | Pin |
| --- | --- |
| Scorer | `regexbench` 0.4.0, commit `05d7547b1a71e6dd5cb00d71bf4dac7732be3ecd` |
| Python | 3.11 |
| Corpus | `RegexEval.json` from `s2e-lab/RegexEval@master` |
| Models | full slug, e.g. `openai/gpt-4o-mini` |
| Sampling | temperature 0.0, max_tokens 200, `k=1` (preview) |

`regexbench` 0.4.0 is **not on PyPI** — `pip install regexbench==0.4.0`
does not resolve to it. The pin is a git commit for that reason, and it
matters: 0.4.0 changed how some patterns are scored relative to 0.3.0.

### Can I check your numbers without trusting you?

Yes, and it costs nothing:

```bash
make setup && make score
```

The scorer reads only `predictions/` — the committed raw responses. No API
key, no model calls. `make check` additionally fails if the recomputed
numbers differ from the published ones, and runs in CI on every push, so
the README cannot drift away from its evidence.

If you disagree with a judgement call — the wrapper rule, say — change it
and re-score. The raw responses are all there, which is the point of
committing them.

### What's wrong with the preview, in our own words?

1. **Ten tasks is not a ranking.** Roughly ±30 points of uncertainty. The
   ordering should not be cited.
2. **`k=1`** means the `@k` metrics carry no information about consistency.
3. **One corpus**, which is old enough to be in every model's training
   data. A high score may partly measure memorisation. A small private task
   set is planned to size that gap — the difference between public and
   private scores is itself the finding.
4. **`mistral-small` has no data** — a provider outage, not a result. It
   needs re-running before any comparison involving it.
5. **No `crosscheck()` pass yet.** `regexbench` 0.4.0 can verify its
   equivalence engine string-by-string against Python's own `re`; the full
   run should use it on the controls as an independent check.

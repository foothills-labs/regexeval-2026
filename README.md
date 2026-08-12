# regexleaderboard

**How good are language models at writing regular expressions you could
actually ship?**

Most regex benchmarks ask one question: does the pattern pass the tests?
This one asks whether you could put the answer in production — because a
pattern can pass every test it was given and still be wrong, or still hang
your server.

**11 models · 450 tasks · 3 samples each · 14,850 calls · run 2026-08-12**

---

## The result

Every model passes roughly **40%** of tasks. Every model produces something
shippable on roughly **20%**. That gap is the finding.

| Model | usable@3 | pass@3 | vulnerable@3 | failed | $/task |
| --- | ---: | ---: | ---: | ---: | ---: |
| `moonshotai/kimi-k3` | **24.8%** | 47.2% | 14.1% | 16/1350 | $0.001328 |
| `anthropic/claude-opus-5` | **23.0%** | 47.5% | 15.5% | 36/1350 | $0.002514 |
| `qwen/qwen3.6-max-preview` | **21.6%** | 42.4% | 9.1% | 0/1350 | $0.000388 |
| `openai/gpt-5.6-sol` | **21.1%** | 42.2% | 10.2% | 1/1350 | $0.002108 |
| `deepseek/deepseek-v4-flash-0731` | **19.8%** | 38.0% | 12.0% | 0/1350 | $0.000026 |
| `qwen/qwen3.6-plus` | **19.8%** | 39.8% | 9.8% | 0/1350 | $0.000121 |
| `z-ai/glm-5.2` | **18.7%** | 42.4% | 14.2% | 0/1350 | $0.000158 |
| `openai/gpt-5.6-luna` | **18.7%** | 39.3% | 11.8% | 1/1350 | $0.000043 |
| `openai/gpt-5.6-terra` | **18.7%** | 42.2% | 12.0% | 0/1350 | $0.000406 |
| `anthropic/claude-sonnet-5` | **18.0%** | 40.7% | 10.9% | 0/1350 | $0.000932 |
| `google/gemini-3.1-flash-lite` | **17.1%** | 38.7% | 12.0% | 0/1350 | $0.000090 |

**Three numbers, one story.** `pass@3` is what other benchmarks report —
did it satisfy the examples. `vulnerable@3` is how many answers can be
made to hang. `usable@3` is what survives once you remove the vulnerable
patterns *and* the ones provably describing a different language than the
reference.

Two things worth noticing more than the ranking:

- **The spread is narrow — 17.1% to 24.8%.** Eleven models across a 100×
  price range land within eight points of each other.
- **`deepseek-v4-flash-0731` costs $0.000026 per task and scores 19.8%.
  `claude-opus-5` costs $0.002514 — 97× more — and scores 23.0%.** Three
  points for two orders of magnitude.

*More metrics — semantic equivalence, exact match, the decidable subset —
are in [APPENDIX.md](APPENDIX.md).*

---

## Why "passes the tests" isn't enough

### It passed every test and it can hang your server

> **Task:** *"tests the validity of a domain or hostname"*

`claude-opus-5` answered:

```
^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(com|org|net|mil|edu)$
```

That is **100% correct** on every example it was given. It is also
**exponentially** vulnerable:

> *a quantifier wraps a quantified group — exponential backtracking on a
> failing suffix*

This is a realistic, production-looking pattern. Put it on a signup form
and you have a denial-of-service bug. **135 such patterns** appeared across
the run: correct, and unsafe.

### It passed every test and it's still wrong

> **Task:** *"Matches 5 numeric digits, such as a zip code."*

`claude-opus-5` answered `\b\d{5}\b` where the reference is `^\d{5}$`.
Both pass the tests. They are not the same pattern, and here is the string
that proves it:

```
"\n00000"
```

The model's version matches a zip code sitting on the second line of a
multi-line string; the reference doesn't. Whether that matters depends on
your input — which is exactly why the benchmark reports it rather than
silently calling one of them correct. **806 answers** passed their tests
while describing a different language than the reference.

---

## The most interesting failure is ours

Some of what we score as "wrong" is the model being **right** and the
human-written reference being wrong.

> **Task:** *"A very simple ISBN validation expression — it just checks for
> a 10 digit number"*

| | |
| --- | --- |
| `claude-opus-5` wrote | `^\d{9}[\dX]$` |
| The reference says | `^\d{9}[\d\|X]$` |
| They differ on | `000000000\|` |

The reference's character class contains a literal **pipe** — someone wrote
`[\d|X]` meaning "a digit or X" and accidentally allowed `|` too. The model
is correct. The gold answer has a typo. We score the model down for it.

Another: for *"Positive integer value."* the model wrote `^[1-9][0-9]*$`
and the reference `^\d+$`, differing on `0`. Zero is not a positive
integer. The model is arguably right there too.

We have not audited how often this happens, so **treat `dfa-eq` as a lower
bound on model correctness, not a verdict on it.** Publishing this is
cheaper than having someone else find it.

---

## Verify it yourself

Every model response is committed in `predictions/`. Scores are computed
from those files and nothing else, so you can recheck the arithmetic
without an API key, without spending anything, and without trusting us:

```bash
git clone https://github.com/foothills-labs/regexleaderboard
cd regexleaderboard
make setup    # installs the pinned scorer, downloads the corpus
make score RUN=sweep
```

`make check` does the same and **fails** if the recomputed numbers differ
from the published ones. It runs in CI on every push against the fast
preview run, so the scoring path cannot silently drift.

---

## Failures are results too

**54 of 14,850 calls failed (0.36%).** They are in the table, not dropped.

**`claude-opus-5` was refused by a content filter on 29 calls** — and the
prompts are benign:

| Task | Prompt |
| --- | --- |
| regexeval/146 | strings that do not contain a single quotation mark |
| regexeval/251 | a six character "password" of numbers and letters |
| regexeval/660 | a series of hex codes separated by spaces |
| regexeval/693 | **"Matches a file extention."** |

No other model refused anything. And it isn't consistent: several of these
were refused on one sample and answered on the next two — same prompt,
same model, same settings. `k=3` sampling surfaced that; `k=1` would have
recorded it as a flat failure.

The remaining failures: 11 calls hit the account's spending limit (see
below) and 4 came back without a resolved provider, which we reject rather
than score, because a row without provenance is not reproducible.

## Known gaps in this run

- **Coverage is not perfectly uniform.** Nine models cover all 450 tasks.
  `kimi-k3` covers 447 — the budget ran out mid-collection. `claude-opus-5`
  covers 445, from the content-filter refusals. Under 1%, no ranking
  changes, but the denominators differ.
- **The reference answers contain errors** (see above), so `dfa-eq`
  understates model correctness by an unmeasured amount.
- **"Not vulnerable" is a screening result, not a proof** — no known-bad
  shape and no blow-up on the attack strings tried.
- **The corpus is old enough to be in training data**, so scores may partly
  measure memorisation. A private task set to measure that gap is not yet
  built.

## What's here

```
predictions/   every raw model response — the evidence
results/       scores, recomputed from predictions/ by CI
runner/        the OpenRouter client, scorer, auditor
METHODOLOGY.md how it was run and every judgement call
APPENDIX.md    the harder metrics and the honest limitations
```

Scoring by [`regexbench`](https://github.com/foothills-labs/regexbench)
(Apache-2.0), pinned to commit `05d7547b`. Corpus:
[Re(gEx|DoS)Eval](https://github.com/s2e-lab/RegexEval), not redistributed
here — `make setup` fetches it.

## License

Code Apache-2.0.

# regexleaderboard

**How good are language models at writing regular expressions that you
could actually ship?**

Most regex benchmarks ask one question: does the pattern pass the tests?
This one asks whether you could put the answer in production — because a
pattern can pass every test it was given and still be wrong, or still hang
your server.

---

## The benchmark in two examples

Every task gives the model a plain-English description. The model writes a
regex. Then we check it three ways.

### Example 1 — it passes every test and it's still wrong

> **Task:** "validate that an uploaded file's extension is jpg, gif or png"

gpt-4o-mini answered `\.(jpg|gif|png)$`. It matched every example it was
given and rejected every counterexample: **100% correct**.

It is still wrong, and here is the proof:

```
.GIF
```

The human-written reference accepts uppercase extensions. This answer
doesn't. The task's test strings happened to be all lowercase, so **the
tests could not possibly have caught this.** We catch it by comparing the
model's pattern against the reference as *languages* — not as text — and
when they differ, the benchmark hands you the shortest string that tells
them apart.

### Example 2 — it passes every test and it can hang your server

> **Task:** "match a french phone number with or without the international
> dialling code"

gpt-4o-mini answered:

```
(?:\+33|0)[1-9](?:[ .-]?[0-9]{2}){4}
```

Also **100% correct**. Also dangerous:

> *a bounded quantifier wraps an unbounded one — the bound caps the
> repetitions but each one can still match many ways*

That's a ReDoS vulnerability: a hostile input makes it take far longer
than it should. Ship it on a public form and you have a denial-of-service
bug.

**Neither of these two answers is usable. Both score 100% on correctness.**
That gap is the entire reason this leaderboard exists.

---

## Results

> ### ⚠️ Preview — not a ranking
>
> This is a **10-task, 4-model pilot** run on 2026-08-11 to prove the
> pipeline works and to price the real run. Ten tasks means roughly ±30
> points of uncertainty. **Do not cite this ordering.** The full run is 762
> tasks across ~13 models.

| Model | usable@1 | pass@1 | vulnerable@1 | failed requests | $/task |
| --- | ---: | ---: | ---: | ---: | ---: |
| `openai/gpt-4o-mini` | **10.0%** | 40.0% | 20.0% | 0/10 | $0.000038 |
| `qwen/qwen-2.5-7b-instruct` | 0.0% | 10.0% | 10.0% | 0/10 | $0.000047 |
| `meta-llama/llama-3.1-8b-instruct` | 0.0% | 20.0% | 0.0% | 0/10 | $0.000003 |
| `mistralai/mistral-small-3.2-24b` | — | — | — | **10/10** | — |

**Three numbers, and they tell one story.** `pass@1` is what other
benchmarks report — did it pass the tests. `vulnerable@1` is how many
answers can be made to hang. `usable@1` is what's left once you remove
both the vulnerable patterns and the ones proven to mean something
different from the reference.

gpt-4o-mini passes 40% of tasks. **10% are shippable.**

`mistral-small` has no numbers because its provider was rate-limited and
we refuse to silently substitute a different one — see
[why a failure is reported, not dropped](#failures-are-results-too).

*More metrics — semantic equivalence, exact match, the decidable subset —
are in [APPENDIX.md](APPENDIX.md). They're real and they're published;
they're just not what you need to read the table.*

---

## Verify it yourself

Every model response is committed in `predictions/`. The scores are
computed from those files and nothing else, so you can recheck our
arithmetic without an API key, without spending anything, and without
trusting us:

```bash
git clone https://github.com/foothills-labs/regexleaderboard
cd regexleaderboard
make setup    # installs the pinned scorer, downloads the corpus
make score    # recomputes every number in the table above
```

Two commands, from a clean clone. `make check` does the same and **fails**
if the recomputed numbers differ from the ones published here — it runs in
CI on every push, so the table above cannot silently drift from the
evidence behind it.

To collect fresh predictions (this one costs money — about $0.001 for the
preview):

```bash
export OPENROUTER_KEY=sk-or-...
make collect
```

---

## Failures are results too

`mistral-small-3.2` answered **none** of its ten tasks. Its provider
returned rate-limit errors, and our requests are pinned to a specific
provider with `allow_fallbacks: false` — so rather than quietly rerouting
to a different company running the same model at a different precision,
the request failed and we recorded it.

This matters more than it sounds. By default, OpenRouter spreads requests
across whichever provider is cheapest right now, and different providers
serve the same model at different quantizations. An unpinned benchmark
measures the router, not the model, and its numbers can change next week
with no code change and no way to notice. So we pin the provider, and we
record which provider *actually* served each request — the pin is the
instruction, the response is the evidence.

A model that errors, refuses, or returns prose instead of a pattern stays
in the table with its failure rate visible. Dropping it would turn a
finding into missing data.

---

## How we know the scorer isn't lying

A scorer that silently returns zeros looks exactly like a model that
failed. So three fake answers ride through the identical scoring path in
every single run:

| Control | What we submit | Must come back as |
| --- | --- | --- |
| known-good | the task's own reference answer | passes, usable |
| known-bad | `z{5}` | fails everything |
| known-vulnerable | `(a+)+b` | flagged vulnerable |

If any control misbehaves, the run is thrown away rather than published.
All four models' controls passed — **including `mistral-small`**, which is
how we know its zeros are a collection failure and not a scoring bug.

---

## What's here

```
predictions/   every raw model response, committed — the evidence
results/       the scores, recomputed from predictions/ by CI
runner/        the OpenRouter client and the scorer
METHODOLOGY.md how it was run, and every judgement call we made
APPENDIX.md    the harder metrics and the honest limitations
PLAN.md        validation of the founding brief, and the plan
```

Scoring is done by [`regexbench`](https://github.com/foothills-labs/regexbench)
(Apache-2.0), pinned to commit `05d7547b`. This repo does not vendor it and
does not reimplement it.

## Limits, stated plainly

- **"Not vulnerable" is a screening result, not a proof.** It means we found
  no known-dangerous shape and it didn't blow up on the attack strings we
  tried.
- **Some comparisons are impossible, not just hard.** For patterns using
  backreferences, asking "are these two the same language" has no
  algorithmic answer. Those tasks are counted honestly rather than quietly
  dropped — see APPENDIX.md.
- **The corpus is old enough to be in training data**, so a high score may
  partly measure memorisation. A small private task set is planned to
  measure that gap.

## License

Code Apache-2.0. The Re(gEx|DoS)Eval corpus is not redistributed here;
`make setup` downloads it from
[s2e-lab/RegexEval](https://github.com/s2e-lab/RegexEval).

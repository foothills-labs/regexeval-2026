# What we learned measuring 11 language models on regular expressions

*Draft for review — Foothills Labs, 2026-08-12*

This is not a leaderboard. We set out to build one and the data told us not
to. What we have instead is a set of findings that hold across every model
we tested, plus an honest account of which of our own measurements we trust
and which we don't.

**The run:** 11 current models, 450 tasks, 3 attempts each, 14,850 requests,
$10.95. Every raw response is committed. Every number recomputes offline
from those files.

---

## 1. The setup, in one page

Each task gives a model a plain-English description of a text pattern:

> *"Matches 5 numeric digits, such as a zip code."*

The model writes a regular expression. Nothing else — no examples, no
hints, no second chance at the format. Then we ask three questions about
its answer, and it's worth being precise about them because they turn out
to have very different reliability.

**Question 1 — does it work?** The task ships strings that should match and
strings that shouldn't. We run the model's pattern against them with
Python's real regex engine.

**Question 2 — does it mean the right thing?** Each task also has a
human-written "gold" answer. We compile both patterns into automata and
compare them as *languages*, not as text. This matters because `[0-9]+` and
`[0-9][0-9]*` are the same pattern written two ways — a benchmark that
compared strings would mark one of them wrong.

**Question 3 — is it safe?** Some regexes take exponentially long on
hostile input. This is a real and well-known denial-of-service bug class
called **ReDoS**. We screen every pattern for the shapes that cause it, and
then actually try to trip it with attack strings.

The key structural fact, which drives everything below: **Questions 1 and 3
never look at the human gold answer.** They run the real engine against
real strings. Question 2 is entirely a comparison against a human. That
difference turns out to matter enormously.

---

## 2. What we found

### 2.1 Passing the tests is about twice as easy as being shippable

| | across all 11 models |
| --- | --- |
| Passes the provided tests | 38.0–47.5% |
| Passes **and** is safe **and** matches the gold's meaning | 17.1–24.8% |

Every model, at every price point, loses roughly half of its apparent
successes to the other two questions. The cheapest open-weights model and
the most expensive frontier model behave the same way here.

### 2.2 About one in ten passing regexes can hang your server

This is the finding we'd lead with, and the one nobody else reports.

Asked to *"test the validity of a domain or hostname"*, Claude Opus 5
produced this:

```
^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(com|org|net|mil|edu)$
```

It passes every test it was given. It is also **exponentially**
vulnerable — a quantifier wrapping a quantified group, which is the classic
catastrophic-backtracking shape. Feed it a long, nearly-valid hostname that
fails at the very end and the matcher explores an exponential number of
paths before giving up.

This is not an exotic pattern. It is the kind of thing that passes code
review because it *looks* careful. We found **135 of these** across the
run — counted as model-task pairs where the answer passed every test *and*
screened as unsafe.

Per model, 9.1–15.5% of answers were vulnerable.

### 2.3 The humans were just as unsafe — and this is the real story

Here is the number that reframes the finding. We screened the **450
human-written gold answers** from the corpus using the identical check:

| | vulnerable | exponential | polynomial |
| --- | ---: | ---: | ---: |
| **Human reference answers** | **13.6%** | 6.4% | 7.1% |
| `kimi-k3` | 10.7% | 5.4% | 5.4% |
| `claude-opus-5` | 10.6% | 7.4% | 3.2% |
| `gemini-3.1-flash-lite` | 9.8% | 5.1% | 4.7% |

**The models are not worse than the humans. They are slightly better, and
in the same ways.**

So the honest headline is not "AI writes dangerous regexes." It is:

> **Dangerous regexes are endemic to how people write regexes, and models
> have faithfully learned that from us.**

That is a more interesting claim and a more defensible one. It also
explains *why* the problem persists: the training data is full of patterns
that look fine, pass their tests, and are exploitable — because that is what
the human-written internet contains.

A note on the vulnerability split: an ICPC 2024 study found LLM-generated
regexes skew toward *polynomial* ReDoS, the cheaper family to overlook. Our
data is more mixed — Claude Opus 5 skews exponential (7.4% vs 3.2%), the
others are roughly even. We report this without a strong claim; the
sub-categories are small enough that we would not lean on the difference.

### 2.4 Paying 97× more buys about three points

| Model | usable | cost per task |
| --- | ---: | ---: |
| `deepseek-v4-flash-0731` | 19.8% | **$0.000026** |
| `claude-opus-5` | 23.0% | **$0.002514** |

Ninety-seven times the price for roughly three percentage points, which is
at the edge of what our data can even resolve. The whole field — frontier
and open-weights, across a 100× price range — fits inside eight points.

For regex generation specifically, model choice is close to a rounding
error and cost is not.

### 2.5 One model refuses harmless prompts, inconsistently

`claude-opus-5` was blocked by a content filter on **29 requests**. The
prompts:

| Task | Prompt |
| --- | --- |
| regexeval/146 | strings that do not contain a single quotation mark |
| regexeval/251 | a six character "password" of numbers and letters |
| regexeval/660 | a series of hex codes separated by spaces |
| regexeval/693 | **"Matches a file extention."** |
| regexeval/742 | "Usefull for SQL update and insert sentence" |

Some are faintly security-adjacent — quote escaping, SQL, passwords. *"Matches
a file extention"* is not. No other model refused anything at all.

And it is **not deterministic**: several of these were refused on one
attempt and answered on the next two, with identical settings. We only know
that because we sample three times; a single-sample benchmark would have
recorded a flat failure and moved on.

---

## 3. What we found about our own measurement

We think this section is as valuable as the results, and we'd rather
publish it than have someone else discover it.

### 3.1 Question 2 is mostly not measuring the model

Question 2 compares the model's pattern to a human's. That only tells you
about the model if the human was right. We sampled 60 cases where a model
**passed every test** but was scored as meaning something different, and
worked through 14 in detail.

| Who was actually wrong | Share |
| --- | ---: |
| The **human gold answer** | 36% |
| **Neither** — the prompt never said | 43% |
| The **model** | 21% |

Separately, **32% of all disagreements** differ only on non-ASCII input —
the model wrote `[0-9]` where the gold wrote `\d`, which in Python also
matches Arabic-Indic digits like `٣`. True, and not a meaningful error.

Combining these, **the model is clearly at fault in roughly 15%** of what
this metric counts against it.

*A caveat we want stated rather than buried: this adjudication is 14 cases,
judged by us, on our own benchmark. The direction is strong enough to act
on and the reasoning for each case is recorded in
`results/sweep/disagreements.json` so it can be disputed. But before anyone
cites "15%" as a figure, a larger sample should be judged by someone with
no stake in the answer. The file is structured for exactly that — every
unadjudicated case has an empty verdict field.*

**Examples of gold answers being wrong:**

> *"It just accepts only positive numbers."*
> The gold answer accepts `0`. Zero is not a positive number. The model
> excluded it and was marked down.

> *"A very simple ISBN validation expression — checks for a 10 digit number."*
> The gold is `^\d{9}[\d|X]$`. That character class contains digit, **pipe**,
> and X — someone wrote `|` meaning "or" inside brackets, where it is just a
> literal character. The model wrote `^\d{9}[\dX]$`, which is what the prompt
> describes, and lost.

> *"Make sure commas are in the rite place (if present)."*
> The gold is `^\$?\d{1,3}(,?\d{3})*(\.\d{1,2})?$`. The `,?` makes the comma
> optional, so it accepts `0,000000` — defeating the entire point of the
> pattern. The model enforced comma placement and was marked different.

**Example of the prompt being ambiguous:**

> *"Matches any single upper- or lower-case letter."*
> A model wrote `[A-Za-z]`. The gold is `^[a-zA-Z]$`. The difference is
> anchoring — whether the *whole string* must be one letter, or whether one
> letter must appear *somewhere*. The prompt does not say. The corpus
> assumes whole-string validation; the sentence doesn't.

We checked whether anchoring alone explained the failures: it accounts for
only ~6%, so this is diffuse mismatch rather than one fixable bug.

**What this means practically:** our `pass` and `vulnerable` numbers are
trustworthy — they never consult the gold. Our "meaning" number, and the
combined `usable` number that includes it, are **lower bounds on model
correctness** by an amount we can estimate but not precisely correct for.

### 3.2 The corpus loads correctly — that isn't the problem

To rule out a pipeline fault, we scored every gold answer against its own
tests: **449 of 450 pass.** The corpus, its matching semantics and its
dialect all load correctly. The problem isn't that we're running it wrong.
The problem is that a gold answer can pass its own tests and still not match
its own description.

### 3.3 The corpus can barely tell these models apart

**62% of tasks give every one of the 11 models the identical outcome** —
all succeed or all fail. Only about 167 of 450 tasks do any work
distinguishing models.

We also initially compared models with the wrong statistical test, treating
them as independent samples when they all answered the *same* questions.
Correcting to a paired comparison (bootstrapping over tasks, so that task
difficulty cancels) changed the picture substantially:

| | pairwise comparisons resolved, of 55 |
| --- | --- |
| Independent intervals (wrong) | 1 |
| Paired bootstrap (correct) | 9 on `usable`, 15 on `pass` |

So the best model is distinguishable from seven of the other ten. The
middle of the table is genuinely inseparable and we won't pretend
otherwise.

**Bands are defensible. A numbered ranking is not.** That is the single
biggest reason this is not published as a leaderboard.

### 3.4 What we did not test

- **Contamination.** This corpus predates every model here and is almost
  certainly in their training data. Some of what we measured may be
  memorisation. We have no private task set, so we cannot size it.
- **Thinking vs. not.** We ran a comparison on 12 tasks, which is
  anecdotal. The main run has reasoning disabled throughout so that models
  which cannot reason are compared fairly against models that can. Whether
  reasoning helps here is open.
- **Prompt sensitivity.** One prompt, unchanged for all models. We don't
  know how much the numbers move under rephrasing.

---

## 4. How to check us

Every model response is committed. Scores are computed from those files and
nothing else — no API key, no cost, no need to trust us:

```bash
git clone https://github.com/foothills-labs/regexleaderboard
cd regexleaderboard
make setup
make score RUN=sweep
```

We verified this ourselves the hard way: wiped to a clean checkout,
reinstalled the pinned scorer, re-downloaded the corpus, re-scored from
scratch, and confirmed **every metric came out identical**. CI runs a
version of that check on every push.

Each request was pinned to a single named provider with fallbacks refused,
because OpenRouter otherwise load-balances across providers that serve the
same model at different numerical precision — which would mean measuring the
router rather than the model. We recorded which provider actually served
every response, and all 11 models were served entirely by the endpoint they
pinned.

Three synthetic controls ride through the scoring path on every run: a
known-good answer that must pass, a known-bad one that must fail, and a
known-vulnerable one that must be flagged. If any misbehaves the run is
discarded. This catches the failure where a scorer silently returns zeros,
which looks exactly like a model that failed.

---

## 5. What we'd say the takeaways are

1. **Regexes that pass their tests are not safe to ship.** About one in ten
   is exploitable, across every model we tested.
2. **This is a human problem that models inherited.** The human-written
   reference answers are *more* vulnerable (13.6%) than the models'
   answers. The training data taught them this.
3. **For this task, model choice barely matters and price matters a lot.**
   A 97× cost difference buys about three points.
4. **Benchmarks that compare against a human answer key are measuring the
   answer key too.** In our sample, only about a fifth of the "wrong
   meaning" verdicts were actually the model's fault. We would encourage
   anyone reporting a similar metric to sample their disagreements and
   check.
5. **Safety filters fire on benign technical prompts**, inconsistently
   enough that a single sample can't detect it.

The most useful thing we can offer other people building evaluations is
point 4, and the practice behind it: **separate the metrics that consult a
human answer key from the metrics that don't, and trust them differently.**

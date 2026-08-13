# The regex your model wrote passes every test. It can also take down your server.

*Foothills Labs · 2026-08-12*

Here is a regular expression. It validates domain names. It was written by
Claude Opus 5, one of the best models available today, and it passes every
test the benchmark gave it.

```
^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(com|org|net|mil|edu)$
```

Read it the way you would in a code review. It anchors both ends. It caps
label length at 63 characters, which is correct. It checks the top-level
domain against a list. It looks like someone was paying attention.

Now look at the outer group. `(...)+` wraps a group that already contains
`{0,61}`. That is the shape that makes a regex engine catastrophically
slow. Feed it a long, almost-valid hostname that fails at the very last
character, and the matcher will try exponentially many ways to divide the
input before it concludes there is no match. Put this on a signup form and
you have handed anyone who notices a denial-of-service button.

This is called ReDoS, it is well documented, and nobody would ship it on
purpose. It shipped here because it passed its tests, and because it looks
careful.

We wanted to know how often that happens. So we asked eleven current
language models to write 450 regular expressions each, three times over,
and then we checked their answers three different ways.

---

## What we did

The setup is simple enough to describe in a sentence. Each task gives a
model a plain-English description — *"Matches 5 numeric digits, such as a
zip code"* — and the model writes a pattern. No examples, no hints, no
second chance. The same instruction for every model.

We used **Re(gEx|DoS)Eval**, a corpus of 762 regex problems collected from
real users, each with a description, strings that must match, strings that
must not, and a human-written answer. We ran 450 of them, spread evenly
across the corpus. Eleven models, from the most expensive frontier systems
to open-weights models costing a hundredth as much. Three attempts each.

That is 14,850 requests and $10.95.

Then we asked three questions about every answer:

**Does it work?** Run it against the strings that should match and the
strings that shouldn't.

**Does it mean the right thing?** Compare it to the human answer as a
*language*, not as text — because `[0-9]+` and `[0-9][0-9]*` describe
exactly the same set of strings and a benchmark comparing text would call
one of them wrong.

**Is it safe?** Screen it for the shapes that backtrack catastrophically,
then actually try to break it with attack strings.

Most regex benchmarks ask only the first question. The third is the one we
built this for.

---

## Passing is about twice as easy as shipping

Across all eleven models, roughly **40% of answers pass their tests**. And
roughly **20% survive all three questions**.

| Model | passes tests | actually usable | vulnerable |
| --- | ---: | ---: | ---: |
| `kimi-k3` | 47.2% | 24.8% | 14.1% |
| `claude-opus-5` | 47.5% | 23.0% | 15.5% |
| `qwen3.6-max-preview` | 42.4% | 21.6% | 9.1% |
| `gpt-5.6-sol` | 42.2% | 21.1% | 10.2% |
| `deepseek-v4-flash-0731` | 38.0% | 19.8% | 12.0% |
| `qwen3.6-plus` | 39.8% | 19.8% | 9.8% |
| `glm-5.2` | 42.4% | 18.7% | 14.2% |
| `gpt-5.6-luna` | 39.3% | 18.7% | 11.8% |
| `gpt-5.6-terra` | 42.2% | 18.7% | 12.0% |
| `claude-sonnet-5` | 40.7% | 18.0% | 10.9% |
| `gemini-3.1-flash-lite` | 38.7% | 17.1% | 12.0% |

Half of what looks like success does not survive contact with the other two
questions. That holds for the most expensive model on the board and the
cheapest, which is the first sign that this is not really a story about
model quality.

We found **135 patterns that passed every test and were exploitable**. Not
exotic ones. Email validators, hostname validators, a pattern for matching
comma-separated names. The kind of thing that gets approved.

---

## The part we did not expect

If you have read this far you have probably formed a conclusion: language
models write dangerous regular expressions. It is the obvious reading and
we were ready to publish it.

Then we ran the same safety check on the **human-written answers** in the
benchmark — the reference patterns the corpus uses as its gold standard,
written by people, for a benchmark about regular expressions.

**13.6% of them are vulnerable.**

The models range from 7.3% to 10.7%. Pooled across all eleven, 9.0%.

| | vulnerable |
| --- | ---: |
| **Human reference answers** | **13.6%** |
| Best model (`qwen3.6-max-preview`) | 7.3% |
| Worst model (`kimi-k3`) | 10.7% |
| All models pooled | 9.0% |

Every single model is safer than the answer key.

So the finding is not that AI writes dangerous regexes. It is:

> **Dangerous regular expressions are endemic to how people write them, and
> the models learned that faithfully from us.**

We prefer this version, and not because it is kinder to the models. It is
more useful. "AI is bad at X" tells you to wait for a better model. This
tells you the problem is in the training data, which is the entire
human-written internet, which means it is not going to be trained away by
itself. If you want safe regular expressions you have to check for it,
because neither the model nor the person it learned from is checking.

---

## Paying more buys almost nothing

The eleven models span roughly a hundredfold range in price.

| Model | usable | cost per task |
| --- | ---: | ---: |
| `deepseek-v4-flash-0731` | 19.8% | $0.000026 |
| `claude-opus-5` | 23.0% | $0.002514 |

DeepSeek's model costs **98× less** and scores about three points lower —
a gap so small our own statistics can barely resolve it. The whole field
fits inside eight percentage points.

For this task, specifically, model choice is close to a rounding error and
cost is not. We would not generalise that to anything else; it is a claim
about writing regular expressions and nothing more.

---

## Then we checked our own work

This is the part we nearly did not write, and the part we now think is the
most valuable.

The second question — *does it mean the right thing?* — compares the
model's pattern against a human's. That only tells you something about the
model if the human was right.

We drew a random sample of sixty cases where a model passed every test but
was scored as meaning something different, and worked through fourteen of
them carefully. We expected to find models making subtle mistakes.

| Who was actually wrong | Share |
| --- | ---: |
| The human answer | 36% |
| Neither — the prompt never said | 43% |
| The model | 21% |

Some examples, because this is more convincing than the summary.

**The task said "it just accepts only positive numbers."** The human answer
was `^\d+([.,]?\d+)?$`, which accepts `0`. The model wrote a pattern that
excludes zero. Zero is not a positive number. The model was marked down for
being right.

**The task asked for a simple ISBN check — "a 10 digit number."** The human
answer was `^\d{9}[\d|X]$`. Look inside the brackets: digit, **pipe**, X.
Someone wrote `|` meaning "or", inside a character class, where it is just
the pipe character. That answer accepts `000000000|` as a valid ISBN. The
model wrote `^\d{9}[\dX]$`, which is what the task described, and lost.

**The task asked for a pattern to "make sure commas are in the rite
place."** The human answer made the commas optional, so it accepts
`0,000000` — defeating the only thing it was for. The model enforced comma
placement and was scored as different.

And in a further 43% of cases, neither answer was wrong, because the
question did not have one right answer. *"Matches any single upper- or
lower-case letter"* — does that mean the whole string is one letter, or
that a letter appears somewhere? The sentence does not say. The benchmark
assumes the first. A model that assumes the second is not making a mistake.

Separately, a third of all the disagreements came down to `\d` versus
`[0-9]`, which differ only on characters like `٣`, the Arabic-Indic three.
Technically a difference. Not one that means anything.

Put together: **the model is clearly at fault in about 15% of what this
metric counts against it.**

We want to be careful here. That number comes from fourteen cases judged by
us, on our own benchmark. The direction is clear enough to act on and every
judgement is written down in the repository so it can be argued with. But
before anyone quotes "15%", somebody with no stake in the answer should
look at a bigger sample.

---

## What we are not claiming

We started out building a leaderboard. We are not publishing one.

When we compared the models properly — accounting for the fact that they
all answered the same questions, which our first analysis got wrong — nine
of the fifty-five possible pairwise comparisons come out distinguishable.
The best model separates from seven of the other ten. The middle of the
table does not separate at all.

There is a structural reason. **62% of the tasks give every single model
the identical result** — they all get it right, or they all get it wrong.
Only about a third of the corpus does any work telling these models apart.

So: bands are defensible. A numbered list from one to eleven is not, and
anyone who re-ran this and got a different order would be right to.

We also could not test contamination. This corpus is old enough to be in
every one of these models' training data, and we have no private task set
to measure how much of what we saw is memory rather than skill.

---

## The thing we would tell other people building evaluations

The two questions that never look at the human answer key — *does it work*
and *is it safe* — are trustworthy. They run a real regex engine against
real strings. Nothing about a flawed answer key can corrupt them.

The question that compares against a human is, in our sample, about 85%
noise from bad answer keys and ambiguous prompts.

We did not design the benchmark around that distinction. We found it by
auditing our own results, and it changed what we were willing to publish.
So the recommendation is simple:

> **Separate the metrics that consult a human answer key from the metrics
> that don't, and trust them differently.**

If you report a metric that compares against gold answers, sample your
disagreements and read them. You may find, as we did, that most of what you
are measuring is not the thing you meant to measure.

---

## Check us

Every response from every model is committed to the repository. The scores
compute from those files and nothing else — no API key, no cost, no need to
take our word for it:

```bash
git clone https://github.com/foothills-labs/regexleaderboard
cd regexleaderboard
make setup
make score RUN=sweep
```

We verified this by wiping to a clean checkout, reinstalling everything,
re-downloading the corpus and re-scoring from scratch. Every number came
out identical. A version of that check runs automatically on every change,
so what is published cannot drift away from the evidence behind it.

Every request was pinned to one named provider and refused substitution,
because the router that sits in front of these models will otherwise serve
you the same model from different companies at different numerical
precision — and then you are measuring the router. All eleven models were
served by exactly the endpoint they were pinned to.

And on every run, three fake answers ride through the scoring alongside the
real ones: a known-good pattern that must pass, a known-bad one that must
fail, and a known-dangerous one that must be flagged. If any of them
misbehaves the run is thrown away. A scorer quietly returning zeros looks
exactly like a model that failed, unless you plant an answer you already
know and check that it comes back the way it should.

---

## What is next

The clearest gap is a task set of our own — a hundred or so problems
written in-house and never published. It would fix three things at once:
the wrong answer keys, the ambiguous prompts, and the contamination we
cannot currently measure. The compute is trivial. The cost is a week of
someone writing carefully, which is the part that actually matters.

The other open question is whether letting these models think helps. We
have a twelve-task comparison, which is too small to mean anything, and one
firm number: turning reasoning on made each request **15.7× more
expensive**. On the easiest task in the corpus — matching a single digit —
one model spent 1,571 tokens of hidden reasoning before answering `^[0-9]$`.
With reasoning off it gave the same answer in ten tokens.

Whether that expense buys accuracy is worth measuring properly. It is
probably its own article.

# Correct and safe are separate properties in generated regular expressions

*Eleven models, two benchmarks, and three results. Plicara Labs · 2026-08-14*

> Eleven current language models wrote 450 regular expressions each, three
> times over, scored three ways: whether the pattern passes its tests,
> whether it means what the task asked for, and whether it is vulnerable to
> regular-expression denial of service. The project began as a leaderboard
> and stopped being one when the metric producing the headline number turned
> out to be measuring the benchmark's own answer key. Three results survived.
> 7.4% of the patterns that work are exploitable. ReDoS prevalence depends on
> whether a pattern was ever executed rather than on whether a human or a
> model wrote it. And on a second benchmark, that 7.4% came back as 16.5%.

Claude Opus 5 produced the following pattern for a domain-name validation
task. It passes every test the benchmark supplies.

```
^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(com|org|net|mil|edu)$
```

Under review it reads as careful work. It anchors both ends, caps label
length at 63 characters, which is correct, and checks the top-level domain
against a list.

The defect is the outer group. `(...)+` wraps a group that already contains
`{0,61}`, which is the construction that makes a backtracking engine
catastrophically slow. Given a long, almost-valid hostname that fails at the
final character, the matcher tries exponentially many ways to divide the
input before concluding there is no match. Deployed on a signup form, the
pattern is a denial-of-service vector.

This is [ReDoS][redos], well enough documented to have its own
[systematisation-of-knowledge paper][sok]. Nobody ships it on purpose. It
shipped here because it passed its tests and because it looks careful.

The question this project set out to answer is how often that happens.

---

## What was already known

We came into this literature late, and most of what we assumed was ours had
already been done by somebody else.

**Somebody already built this benchmark.** The corpus we use is
[Re(gEx|DoS)Eval][corpus], and it comes from a 2024 paper by Mohammed Latif
Siddiq, Jiahao Zhang, Lindsay Roney and Joanna C. S. Santos at Notre Dame
([ICSE-NIER 2024][regexeval-paper]). They collected 762 regex problems from
real user posts, wrote tests and a reference answer for each, and defined
the four measurements we report: does it pass its tests, is it vulnerable to
ReDoS, does it denote the same language as the reference, and is it
character-for-character identical. They then scored T5, Phi-1.5 and
GPT-3.5-Turbo on all of it and reported which model wrote regexes that were
correct *and* secure.

That is our instrument, all of it. We did not invent the joint framing, the
metrics, or the corpus. What we are doing is running their
apparatus on eleven models that did not exist when they built it, taking
their composite metric apart, and pointing their safety check back at their
own answer key.

**Scoring correctness and security together is a live area.** Four
benchmarks published in the last two years do it for general code:
[CWEval][cweval] (119 tasks over 31 CWEs, five languages),
[BaxBench][baxbench] (392 backend tasks with expert-written exploits),
[SecureAgentBench][sab] (105 repository-level tasks aimed at coding agents),
and [DualGauge][dualgauge] (154 tasks, 10 models). They agree on the shape
of the result. BaxBench finds roughly half of functionally correct backends
exploitable. SecureAgentBench reports 15.2% correct-and-secure for its best
agent. DualGauge sees secure-pass@1 under 12% while functional pass@1 clears
50%. The gap between "works" and "safe to ship" is large and well
established.

Before any of those, [Pearce et al.][copilot] generated 1,689 programs in
security-relevant scenarios and found about 40% vulnerable, and [Perry et
al.][perry] ran a user study where people with an AI assistant wrote less
secure code while reporting more confidence in it.

**And people already knew regexes were a problem.** [Davis et
al.][davis2018] measured ReDoS across the npm and PyPI ecosystems.
Siddiq's own [companion study][icpc] looked specifically at ReDoS in
LLM-generated patterns.

What the rest of this article is about:

1. Nobody had run the safety screen on the benchmark's **own human
   reference answers**, or against the regular expressions people ship.
2. Nobody had **audited the reference set** these metrics compare against.
   When we did, the headline number fell apart.
3. Nobody had run any of it on the **current model population**.

And one thing we only did because the first draft of this article deserved
it: we ran the whole measurement again on a **second benchmark**, to see
which of our numbers were about regular expressions and which were about
Re(gEx\|DoS)Eval.

---

## What we did

Each task gives a model a plain-English description, such as *"Matches 5
numeric digits, such as a zip code"*, and the model writes a pattern. It gets
no worked examples and no second attempt, and every model gets the same
instruction.

We ran 450 of the 762 tasks, spread evenly across the corpus so the sample
is not weighted toward the easy end. Eleven current frontier and
open-weights models, the cheapest costing a hundredth of the dearest, three
attempts each.

Then we asked three questions about every answer:

1. **Does it work?** The pattern is run against the strings that should
   match and the strings that shouldn't.

2. **Does it mean the right thing?** The pattern is compared to the human
   answer as a *language* rather than as text, because `[0-9]+` and
   `[0-9][0-9]*` describe exactly the same set of strings and a benchmark
   comparing text would call one of them wrong.

3. **Is it safe?** The pattern is screened for the shapes that backtrack
   catastrophically, then attacked with strings built to trigger them.

The scoring is done by [regexbench][regexbench], a tool we wrote before this
project and pinned to one commit for the run. It is our own instrument, which
is a caveat these results carry rather than one they escape. The equivalence
check inside it is [dk.brics.automaton][brics], which is not ours.

The second and third questions are why this corpus exists rather than the
older regex benchmarks, [KB13][kb13] and [NL-RX][nlrx], which score a
candidate against a reference by language equivalence and stop there.

---

## Passing looks about twice as easy as shipping

Between **38.0% and 46.5% of answers pass their tests**, depending on the
model. Between **17.1% and 23.8% survive all three questions**.

| Model | passes tests | survives all three | vulnerable |
| --- | ---: | ---: | ---: |
| `kimi-k3` | 46.5% | 23.8% | 12.9% |
| `qwen3.6-max-preview` | 42.4% | 21.6% | 9.1% |
| `gpt-5.6-sol` | 42.1% | 20.9% | 10.0% |
| `claude-opus-5` | 46.1% | 20.8% | 13.2% |
| `deepseek-v4-flash-0731` | 38.0% | 19.8% | 12.0% |
| `qwen3.6-plus` | 39.8% | 19.8% | 9.8% |
| `glm-5.2` | 42.4% | 18.7% | 14.2% |
| `gpt-5.6-terra` | 42.2% | 18.7% | 12.0% |
| `gpt-5.6-luna` | 39.2% | 18.5% | 11.6% |
| `claude-sonnet-5` | 40.7% | 18.0% | 10.9% |
| `gemini-3.1-flash-lite` | 38.7% | 17.1% | 12.0% |

Half of what looks like success does not survive contact with the other two
questions, and that holds for the most expensive model on the board as much
as the cheapest.

We also found **390 generations that passed every test and were
exploitable**, out of 5,269 that passed — 7.4%, or 144 of the 2,051
model-task pairs where anything passed at all. They are ordinary things: email
validators, hostname validators, a pattern for matching comma-separated names.
The kind of thing that gets approved.

We were ready to publish that table. It lines up neatly with what BaxBench
and SecureAgentBench found in other domains, and we took the agreement as
confirmation instead of checking it.

---

## Except the gap is not what it looks like

The composite has three conjuncts. Two of them run a real regex engine
against real strings. The third compares against a human's answer. When we
asked which conjunct was actually producing the gap, the split was not close:

| Conjunct removed | Cost to the score |
| --- | ---: |
| Safety | 2.9 points |
| Semantic equivalence | 18.9 points |

**87% of our headline gap comes from the equivalence term.** And the
equivalence term, as the audit further down shows, is 85% noise from
bad reference answers and prompts that never specified the property in
dispute.

Dropping it and scoring only the two criteria that never consult a human
answer key, which is also the construction the general-code benchmarks use,
leaves this:

> **7.4% of the regular expressions that work are ReDoS-vulnerable.**

That number is much smaller than the composite suggested, and it does not
match what the rest of the field reports.

| | functional | correct-and-secure |
| --- | ---: | ---: |
| BaxBench (backends) | — | ~half of correct solutions exploitable |
| SecureAgentBench (repo-level agents) | higher | 15.2% best agent, 9.2% mean |
| DualGauge (specification-only) | >50% | <12% |
| **This work (regexes)** | **38–47%** | **security removes 7.4%** |

The security criterion demolishes most of what passes in those settings. In
ours it takes off a sliver. We have explanations for that and no way to
separate them with this data. A regex is one expression with one failure
mode while a backend has many independently exploitable parts. ReDoS is a
structural anti-pattern, plausibly better represented in training data than
CWE-classified defects are. And our functional pass rate is low enough that
the correct subset may skew toward simple tasks with less room for
catastrophic backtracking.

**We assumed the correctness-to-security penalty transfers between domains,
and it does not.** Worse, our composite showed a penalty of about the
expected size for entirely the wrong reason. If we had reported it without
decomposing, we would have published a right-looking number built on our
least trustworthy measurement.

---

## Surprise, surprise, ground truth is hard

The obvious conclusion at this stage is that language models write dangerous
regular expressions. That was our reading, and we were ready to publish it.
So we turned the same safety screen on the **human-written
answers** in the benchmark, the reference patterns the corpus uses as its
gold standard, written by people, for a benchmark about regular expressions.
**13.6% of them are vulnerable.**

The models range from 7.3% to 10.7%. Pooled across all eleven, 9.0%.

| | vulnerable |
| --- | ---: |
| **Human reference answers** | **13.6%** |
| Best model (`qwen3.6-max-preview`) | 7.3% |
| Worst model (`kimi-k3`) | 10.7% |
| All models pooled | 9.0% |

Every single model is safer than the answer key. As far as we can tell this
comparison had not been run before, and it is only possible because this
corpus ships human answers. The general-code benchmarks execute tests and
exploits instead of comparing against a gold artifact, so they have nothing
to point the screen at.

We were about to draw the obvious conclusion from that: dangerous regular
expressions are endemic to how people write them, and the models learned it
from us. Then we noticed the conclusion rested on one corpus, and that the
corpus in question is an answer key rather than working code.

---

## So we checked five more populations

None of this needs a single API call. The safety screen reads patterns, so
running it on somebody else's corpus costs nothing but CPU. We screened the
gold answers of [KB13][kb13], the machine-generated patterns of
[NL-RX][nlrx], and three corpora from [Davis et al.'s][linguafranca]
artifact: half a million regular expressions **extracted from shipped
packages** across npm, PyPI, Maven, CPAN, crates.io, godoc, packagist and
RubyGems, half a million more **posted to Stack Overflow**, and the 3,838
patterns **published to regexlib.com** for other people to reuse.

The last two matter because Re(gEx\|DoS)Eval was built from real user posts.
If forum snippets are dangerous, then the benchmark's answers are dangerous
for a reason that has nothing to do with benchmarks.

Raw rates are dominated by task mix. This corpus is full of validators, email
and ISBN and hostname, which is exactly the shape that backtracks, while most
regexes in the wild are short fragments with no opportunity to. So the table
below restricts every population to anchored `^...$` patterns, which is the
closest we can get to comparing like with like:

| anchored patterns only | written to be | n | vulnerable |
| --- | --- | ---: | ---: |
| RegexLib, published for reuse | read | 1,684 | 20.1% |
| Stack Overflow answers | read | 4,000 | 17.3% |
| Re(gEx\|DoS)Eval gold answers | read | 538 | 13.4% |
| **our eleven models** | — | 3,613 | **9.8%** |
| **production code** | **run** | 4,000 | **8.9%** |

Real shipped code is safer than every model we tested, so the endemic reading
is wrong and we would have published it. But the more interesting thing is
the column we did not expect to need.

> **The dividing line is not human against machine. It is whether the pattern
> was ever run.**

Everything written to be *read* sits between 13% and 20%. The one population
that has been *executed*, under real traffic, in code somebody installed,
sits at 8.9%. The models sit with it, at 9.8% — a difference that does not
resolve (*p* = 0.20).

The model row is restricted the same way as every other row: we keep only the
models' own anchored outputs. An earlier draft put the models in at their
unrestricted rate, comparing a restricted human population against an
unrestricted machine one, which is exactly the confound the restriction exists
to remove. Fixing it moved the models slightly *toward* the answer key and
away from production code, and the conclusion held anyway.

That is not a story about carelessness. A pattern published to a library, or
posted in an answer, or written to key a benchmark, is authored once to
communicate an idea and then nothing ever happens to it. Nobody profiles it.
Nobody files a bug against it. A pattern inside a shipped package gets run
millions of times, and some of them have been repaired specifically for this,
because Davis and colleagues went and told people. Vulnerability tracks
exposure to execution, and an answer key has none.

It also explains this corpus's answers without blaming whoever wrote them.
They came from forum posts, and forum posts screen at 17.3%. The gold set is
actually *safer* than the population it was drawn from, which suggests the
corpus authors filtered as they went. It still does not get them down to the
level of code that runs.

The practical implication survives with a better reason behind it. Safe
regular expressions require screening at the point of use. Neither a pattern
copied from the internet nor one just produced by a model has been run in
anger.

---

## One place we disagree with prior work

Siddiq's [companion ReDoS study][icpc] reports that LLM-generated patterns
skew toward *polynomial* rather than exponential blow-up. Our models go the
other way, 5.3% exponential against 3.8% polynomial pooled. The cross-corpus
run says where that skew actually lives: in the anchored production sample,
polynomial beats exponential 253 to 105, while the benchmark's gold answers
are near even at 34 to 38.

So the polynomial skew is real, and it is a property of the regular
expressions people ship rather than of the ones models write. On this axis,
too, model output differs from human practice rather than reproducing it.
The subcategory counts on our side are small and we make no strong claim.
Somebody should replicate it. Every count above is in
[`results/cross_corpus_redos.json`][crosscorpus], written by a script in the
repository that needs no API key to re-run.

---

## Paying more buys almost nothing

The eleven models span a 98× range in price.

| Model | survives all three | cost per request |
| --- | ---: | ---: |
| `deepseek-v4-flash-0731` | 19.8% | $0.000026 |
| `claude-opus-5` | 20.8% | $0.002514 |

DeepSeek's model costs **98× less** and scores a point *higher* — a difference
comfortably inside what our own statistics can resolve, which is to say the
two are indistinguishable. The whole field fits inside seven percentage
points.

For this task, specifically, model choice is close to a rounding error and
cost is not. That is a claim about writing regular expressions and nothing
more. Read generously, it is also evidence that regular expressions turn up
often enough and uniformly enough in text that every one of these training
runs picked up about the same competence at them.

---

## We ran the whole thing again on a different benchmark

Everything up to here rests on one corpus. The 7.4% is a fact about
Re(gEx|DoS)Eval until somebody checks it somewhere else, so we checked.

[StructuredRegex][sr] is a second benchmark for the same task, and it has the
one thing the older ones lack: example strings for every problem, both
matching and non-matching. That is sufficient for *does it work*. Its answer
key, written in a notation of its own, is never read, so this run carries no
equivalence score at all. Only the two questions that held up.

Same eleven models, same settings, 622 problems, one answer each, $3.67.

| | Re(gEx\|DoS)Eval | StructuredRegex |
| --- | ---: | ---: |
| passes its tests | 30.0–41.4% | 51.7–66.1% |
| vulnerable | 7.3–10.7% | 13.6–17.9% |
| **vulnerable, of the ones that work** | **7.4%** | **16.5%** |

The finding holds. Patterns that pass their tests and remain exploitable are
not a quirk of one benchmark.

The number does not hold. It more than doubles. And the easy explanation,
that the second benchmark is harder so the answers are worse, is the wrong
way round: StructuredRegex is *easier*, by about twenty points. Its problems
are built out of repetition and optional parts, and models answering those
write more of the shape that backtracks.

We had already argued that this penalty depends on the domain, on the
strength of BaxBench and SecureAgentBench doing something rather different in
other languages. Anyone was free to shrug at that. This is the same task, the
same language, the same screen, the same eleven models, and the answer is
2.2× apart. It is a better version of our own argument and it is aimed at our
own headline number.

The ordering moved too. Sonnet 5 comes first here and sits in the middle of
the other table. Kimi K3 comes first there and eighth here. We already said a
numbered list of eleven models was not defensible. This is what that looks
like under test.

One thing worth reporting because it nearly bit us. Anthropic's content
filter refused 182 of the 622 descriptions for Opus, all of them harmless
("a string that starts with one or more digits and optionally ends with 'NU'
or 'DG'"). Retrying recovered 98. The temptation is to score Opus on what
survived and move on. Instead we checked what the other ten models did on the
problems Opus lost, and those problems turned out to be **8.1 points harder**
than average. So the leftovers flattered Opus, while counting the refusals as
wrong answers punished it, both at once. Every number above is on the 513
problems all eleven models actually answered.

---

## Then we checked our own work

The second question, *does it mean the right thing?*, compares the model's
pattern against a human's. That measures the model only if the human was
right.

This is not a new worry in the abstract. [Northcutt, Athalye and
Mueller][northcutt] audited ten of the most-used test sets in machine
learning and found a mean 3.3% label-error rate, enough in several cases to
flip which model the benchmark said was better. Nobody had asked the
question of this corpus. We have one advantage they did not: our labels are
regular expressions, so a disputed label can be settled by producing a
string the reference and the description disagree about, rather than by
taking a second opinion.

We drew a random sample of sixty cases where a model passed every test but
was scored as meaning something different, and worked through fourteen of
them carefully. We expected to find models making subtle mistakes.

| Who was actually wrong | Share |
| --- | ---: |
| The human answer | 36% |
| Neither, the prompt never said | 43% |
| The model | 21% |

**The task said "it just accepts only positive numbers."** The human answer
was `^\d+([.,]?\d+)?$`, which accepts `0`. The model wrote a pattern that
excludes zero. Zero is not a positive number. The model was marked down for
being right.

**The task asked for a simple ISBN check, "a 10 digit number."** The human
answer was `^\d{9}[\d|X]$`. Inside the brackets: digit, **pipe**, X.
Someone wrote `|` meaning "or", inside a character class, where it is just
the pipe character. That answer accepts `000000000|` as a valid ISBN. The
model wrote `^\d{9}[\dX]$`, which is what the task described, and lost.

**The task asked for a pattern to "make sure commas are in the rite
place."** The human answer made the commas optional, so it accepts
`0,000000`, defeating the only thing it was for. The model enforced comma
placement and was scored as different.

And in a further 43% of cases neither answer was wrong, because the question
did not have one right answer. *"Matches any single upper- or lower-case
letter"*: does that mean the whole string is one letter, or that a letter
appears somewhere? The sentence does not say. The benchmark assumes the
first. A model that assumes the second is not making a mistake.

Separately, a third of all the disagreements came down to `\d` versus
`[0-9]`, which differ only on characters like `٣`, the Arabic-Indic three.
That is a technical difference with no consequence in almost any real use.

Put together: **the model is clearly at fault in far less of this than the
metric counts against it.**

That reading comes from fourteen cases judged by us, on a benchmark we were
using to make a point. The direction is clear enough to act on and every
judgement is written down in the repository so it can be argued with.

---

## What we are not claiming

We started out building a leaderboard. We are not publishing one.

When we compared the models properly, accounting for the fact that they all
answered the same questions, nine of the fifty-five possible pairwise
comparisons come out distinguishable. Our first analysis got that wrong and
resolved exactly one. The fix is not ours either: the paired bootstrap is
[Berg-Kirkpatrick, Burkett and Klein][bkk], following Koehn's
bootstrap-resampling protocol for machine translation, and using it instead
of unpaired intervals is [standard advice][dror]. What we can report is how
much it changes here, which is ninefold.

Even corrected, the best model separates from six of the other ten and the
middle of the table does not separate at all. There is a structural reason.
**62% of the tasks give every single model the identical result**, either
right across the board or wrong across the board. Only 167 of the 450 tasks
do any work telling these models apart.

Bands are defensible. A numbered list from one to eleven is not, and anyone
who re-ran this and got a different order would be right to. So here are the
bands, which are all we will publish:

- **Ahead of at least one model, behind none.** `claude-opus-5`, `kimi-k3`,
  `qwen3.6-max-preview`.
- **No comparison resolves either way.** `deepseek-v4-flash-0731`,
  `gpt-5.6-sol`.
- **Behind at least one model, ahead of none.** `claude-sonnet-5`,
  `gemini-3.1-flash-lite`, `glm-5.2`, `gpt-5.6-luna`, `gpt-5.6-terra`,
  `qwen3.6-plus`.

Read those as statements about each model, not as three rungs. The bands are
not ordered against each other either: `claude-opus-5` is in the first and
`glm-5.2` in the last, and those two are not distinguishable. Only `kimi-k3`
separates from more than two others. Every pairwise interval is in
`results/sweep/paired_intervals.json`.

We are not claiming any of these percentages travel. We used to say the
model numbers rested on one corpus and leave it there. Now we have run two,
and the vulnerability rate among working patterns came out 2.2× apart, so
treat every figure in this article as a fact about the benchmark it was
measured on. *Does it mean the right thing* is still single-corpus and
always will be, because no other benchmark for this task ships an answer key
in ordinary regex syntax.

We also could not test contamination. This corpus was published in 2024 and
built from public forum posts, so it is plausibly inside every one of these
models' training data. [Sainz et al.][sainz] argue that contamination has to
be measured per benchmark rather than waved away, and we agree, and we
cannot do it. We have no private task set. This is the largest hole in the
work.

---

## Which of the three metrics held up

The two questions that never look at the human answer key, *does it work* and
*is it safe*, held up. They run a real regex engine against real strings, and
no defect in an answer key can corrupt them.

The question that compares against a human did not. In our sample it was 85%
noise from bad answer keys and ambiguous prompts.

> **The metrics that consult a human answer key behaved differently from the
> metrics that do not, and only the second kind survived scrutiny.**

Reading the disagreements is what exposed it. Most of what that metric
counted was not the thing it was meant to measure.

---

## Reproduction

Every response from every model is committed to the repository. The scores
compute from those files and nothing else, so reproduction costs nothing and
needs no API key:

```bash
git clone https://github.com/plicara/regexeval-2026
cd regexeval-2026
make setup
make score RUN=sweep
```

We verified this by wiping to a clean checkout, reinstalling everything,
re-downloading the corpus and re-scoring from scratch. Every number came out
identical. A version of that check runs automatically on every change, so
what is published cannot drift away from the evidence behind it.

Every request was pinned to one named provider and refused substitution,
because the router that sits in front of these models will otherwise serve
the same model from different companies at different numerical
precision, at which point the measurement is of the router. [A survey of
AI-safety codebases using one such router][pinning] found 31 of 32 did not
pin the provider. All eleven of our models were served by exactly the
endpoint they were pinned to.

On every run, three fake answers ride through the scoring alongside the real
ones: a known-good pattern that must pass, a known-bad one that must fail,
and a known-dangerous one that must be flagged. If any of them misbehaves the
run is discarded. A scorer quietly returning zeros is indistinguishable from
a set of models that all failed, unless a known answer is planted and checked
on the way through.

---

## What is next

The large open question is whether letting these models think helps. We have
a twelve-task comparison, which is too small to mean anything, and one firm
number: turning reasoning on made each request **15.7x more expensive**. On
the easiest task in the corpus, matching a single digit, one model spent
1,571 tokens of hidden reasoning before answering `^[0-9]$`. With reasoning
off it gave the same answer in ten tokens.

Whether that expense buys accuracy is worth measuring properly. It is
probably its own article.

---

## References

Natural-language-to-regex generation, where language equivalence against a
reference became the standard criterion:

- Kushman & Barzilay. *Using Semantic Unification to Generate Regular
  Expressions from Natural Language.* NAACL-HLT 2013. [aclanthology][kb13]
- Locascio, Narasimhan, DeLeon, Kushman & Barzilay. *Neural Generation of
  Regular Expressions from Natural Language with Minimal Domain Knowledge.*
  EMNLP 2016. [aclanthology][nlrx]

The benchmark and metrics we used:

- Siddiq, Zhang, Roney & Santos. *Re(gEx|DoS)Eval: Evaluating Generated
  Regular Expressions and their Proneness to DoS Attacks.* ICSE-NIER 2024.
  [doi:10.1145/3639476.3639757][regexeval-paper] ·
  [corpus][corpus]
- Siddiq, Zhang & Santos. *Understanding Regular Expression Denial of
  Service (ReDoS): Insights from LLM-Generated Regexes and Developer
  Forums.* ICPC 2024. [doi:10.1145/3643916.3644424][icpc]
- Chen et al. *Evaluating Large Language Models Trained on Code.* 2021.
  [arXiv:2107.03374][codex]. Source of the pass@k estimator.
- Ye, Chen, Dillig & Durrett. *Benchmarking Multimodal Regex Synthesis with
  Complex Structures.* ACL 2020. [aclanthology][sr]. The second corpus.

Joint correctness-and-security benchmarking:

- Peng et al. *CWEval.* LLM4Code 2025. [arXiv:2501.08200][cweval]
- Vero et al. *BaxBench.* ICML 2025. [arXiv:2502.11844][baxbench]
- Chen et al. *SecureAgentBench.* 2025. [arXiv:2509.22097][sab]
- Patir et al. *DualGauge.* 2025. [arXiv:2511.20709][dualgauge]
- Pearce et al. *Asleep at the Keyboard?* IEEE S&P 2022.
  [arXiv:2108.09293][copilot]
- Perry et al. *Do Users Write More Insecure Code with AI Assistants?*
  CCS 2023. [doi:10.1145/3576915.3623157][perry]

ReDoS:

- Davis et al. *The Impact of ReDoS in Practice.* ESEC/FSE 2018.
  [doi:10.1145/3236024.3236027][davis2018]
- Davis, Michael IV, Coghlan, Servant & Lee. *Why Aren't Regular Expressions
  a Lingua Franca?* ESEC/FSE 2019. [artifact][linguafranca], the source of
  the 537,806 production regexes screened here.
- Bhuiyan, Çakar, Burmane, Davis & Staicu. *SoK: A Literature and
  Engineering Review of ReDoS.* AsiaCCS 2025. [arXiv:2406.11618][sok]

Measurement:

- Northcutt, Athalye & Mueller. *Pervasive Label Errors in Test Sets
  Destabilize Machine Learning Benchmarks.* NeurIPS D&B 2021.
  [arXiv:2103.14749][northcutt]
- Berg-Kirkpatrick, Burkett & Klein. *An Empirical Investigation of
  Statistical Significance in NLP.* EMNLP-CoNLL 2012. [aclanthology][bkk]
- Koehn. *Statistical Significance Tests for Machine Translation
  Evaluation.* EMNLP 2004. [aclanthology][koehn]
- Dror et al. *The Hitchhiker's Guide to Testing Statistical Significance in
  NLP.* ACL 2018. [aclanthology][dror]
- Sainz et al. *NLP Evaluation in Trouble.* Findings of EMNLP 2023.
  [aclanthology][sainz]

Tooling, disclosed because two of these are ours:

- [regexbench][regexbench], the scorer. Prior work by this lab, pinned to a
  single commit for this run.
- [dk.brics.automaton][brics], Anders Møller's finite-state automata
  library, which does the language-equivalence check.
- [Not Pinning Your OpenRouter Provider Might Invalidate Your
  Research][pinning], the survey behind the serving-provider discipline.

The full technical write-up, with the statistics, the failure taxonomy and
every adjudicated case, is in [`paper/main.tex`][paper] in the repository.

[redos]: https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS
[corpus]: https://github.com/s2e-lab/RegexEval
[regexeval-paper]: https://doi.org/10.1145/3639476.3639757
[icpc]: https://doi.org/10.1145/3643916.3644424
[sok]: https://arxiv.org/abs/2406.11618
[davis2018]: https://doi.org/10.1145/3236024.3236027
[cweval]: https://arxiv.org/abs/2501.08200
[baxbench]: https://arxiv.org/abs/2502.11844
[sab]: https://arxiv.org/abs/2509.22097
[dualgauge]: https://arxiv.org/abs/2511.20709
[copilot]: https://arxiv.org/abs/2108.09293
[perry]: https://doi.org/10.1145/3576915.3623157
[northcutt]: https://arxiv.org/abs/2103.14749
[bkk]: https://aclanthology.org/D12-1091/
[dror]: https://aclanthology.org/P18-1128/
[sainz]: https://aclanthology.org/2023.findings-emnlp.722/
[codex]: https://arxiv.org/abs/2107.03374
[paper]: https://github.com/plicara/regexeval-2026/blob/main/paper/main.tex
[sr]: https://aclanthology.org/2020.acl-main.541/
[linguafranca]: https://github.com/VTLeeLab/LinguaFranca-FSE19
[crosscorpus]: https://github.com/plicara/regexeval-2026/blob/main/results/cross_corpus_redos.json
[kb13]: https://aclanthology.org/N13-1103/
[nlrx]: https://aclanthology.org/D16-1197/
[koehn]: https://aclanthology.org/W04-3250/
[regexbench]: https://github.com/plicara/regexbench
[brics]: https://www.brics.dk/automaton/
[pinning]: https://www.lesswrong.com/posts/KsyoSAyBRXtwzSugg/

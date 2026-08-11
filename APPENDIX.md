# Appendix — the harder metrics

The README reports three numbers because three numbers tell the story.
These are the rest. They are not hidden — they are computed in every run
and stored in `results/*/`— they just aren't what you need to read the
leaderboard.

## The full metric set

| Metric | Plain English |
| --- | --- |
| `pass@k` | Did the pattern match the examples and reject the counterexamples? |
| `vulnerable@k` | Can the pattern be made to hang on hostile input? |
| `usable@k` | Correct, not vulnerable, and never *proven* to differ from the reference. |
| `dfa-eq@k` | Is it the same language as the reference? Counting "we couldn't tell" as a miss. |
| `dfa-eq@k (decided)` | The same, but only over the tasks where the question could be answered at all. |
| `exact@k` | Is it the identical string to the reference? |

### Why `dfa-eq` is reported twice

Comparing two regexes as *languages* is a solved problem for most patterns:
compile both to automata, compare the machines. But for patterns using
**backreferences** — things like `(a)\1`, "match a thing, then the same
thing again" — it isn't just hard, it's **formally undecidable**. No
algorithm can answer it, ever. Not a limitation of this tool; a theorem.

That leaves an honest reporting problem, and one number can't solve it:

- **`dfa-eq@k`** counts undecidable comparisons as failures. It answers
  *"how much of the corpus did we positively verify as correct?"* It's a
  lower bound, and it cannot flatter a model.
- **`dfa-eq@k (decided)`** drops those tasks from the denominator entirely.
  It answers *"of the questions that could be answered, how many did the
  model get right?"* That's the model's ability, separated from the tool's
  reach.

Publishing only the second one would be quiet inflation — a score over the
easy subset, presented as the whole. Publishing only the first blames the
model for a theorem. So both are published, always, with the count of
undecidable tasks stated alongside.

**In the preview**, 2–4 of 10 tasks per model were undecidable. That's a
large fraction of a small sample, and one more reason not to read the
preview as a ranking.

### Why `exact@k` exists at all

It was 0.0% for every model in the preview — not a single string-identical
answer. That's the point. `[0-9]+` and `[0-9][0-9]*` are the same language
written two ways, and a benchmark that scored by string comparison would
call one of them wrong. `exact@k` is published to show how badly that
approach would misrank everyone, not because it measures anything useful.

## Preview values

| Model | dfa-eq@1 | dfa-eq@1 (decided) | exact@1 | undecidable |
| --- | ---: | ---: | ---: | ---: |
| `openai/gpt-4o-mini` | 10.0% | 12.5% | 0.0% | 2/10 |
| `qwen/qwen-2.5-7b-instruct` | 0.0% | 0.0% | 0.0% | 3/10 |
| `meta-llama/llama-3.1-8b-instruct` | 0.0% | 0.0% | 0.0% | 4/10 |

Semantic equivalence tops out at 12.5% where `pass@1` reaches 40%.
Reproducing the reference *language* is a much harder problem than passing
the examples — which is the case for measuring both.

## The wrapper rule

Models were asked for a bare pattern in a code block. Some return the
pattern wrapped in their host language's string syntax instead:

```
r'\d+$'      ← what the model said
\d+$         ← what it meant
```

Scored literally, `r'\d+$'` is a pattern matching the letter `r`, a quote,
and so on. It fails — for a reason that has nothing to do with regex
ability.

**The rule: we strip one layer of host-language quoting before scoring**
(`r'…'`, `'…'`, `"…"`, `` `…` ``, `/…/flags`), because the benchmark is
measuring regex generation, not output formatting.

This is a judgement call with real consequences, so it's made in the open:

- Llama-3.1-8b wrapped 5 of 10 answers. Scored literally it gets `pass@1`
  0.0%; with the rule applied, **20.0%**.
- Every strip is recorded in `results/*/<model>.json` under
  `wrapped_detail`, with the before and after.
- The unnormalized score is also stored, as `metrics_as_sent`, so anyone
  who thinks the rule is wrong can use the other number without re-running
  anything.
- `wrapped_responses` is published per model, because a model that can't
  follow the output format is telling you something real — it just isn't
  a regex score.

This rule penalizes nobody at random, but it does help small models more
than large ones, since they're the ones that wrap. That's exactly why it's
stated here instead of buried in the code.

## Engine limitations

These belong to the scorer, `regexbench` 0.4.0, and apply to every model
equally:

- **`\d` is not `[0-9]`.** It matches every Unicode digit, because that is
  what Python's `re` does and the scorer runs the real `re`. This is the
  single thing most likely to make our numbers differ from another
  published regex eval.
- **ReDoS screening covers three of five known vulnerability families**
  structurally; the other two are caught only if the empirical pass happens
  to trip them. So `vulnerable@k` is a **lower bound** — the true rate is
  at least this high.
- **Lookaround became decidable in `regexbench` 0.4.0.** Earlier versions
  refused it. Our numbers are therefore not comparable to figures produced
  with 0.3.0 or earlier.
- **Match semantics matter and are set per corpus.** Re(gEx|DoS)Eval's
  references pass 100% of their own tests under "search" semantics and only
  94% under "full match" — pick wrong and you score 46 human-written gold
  answers as failures. We verified the corpus loads correctly by scoring
  every reference against itself: 762/762, `pass@1` 99.9%.

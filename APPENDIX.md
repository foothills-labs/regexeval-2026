# Appendix — the harder metrics

The README reports three numbers because three numbers tell the story.
These are the rest. They are not hidden — they are computed in every run
and stored in `results/sweep/` — they just aren't what you need to read the
leaderboard.

## The full metric set

| Metric | Plain English |
| --- | --- |
| `pass@k` | Did the pattern match the examples and reject the counterexamples? |
| `vulnerable@k` | Can the pattern be made to hang on hostile input? |
| `usable@k` | Correct, not vulnerable, and never *proven* to differ from the reference. |
| `dfa-eq@k` | Is it the same language as the reference? Counting "we couldn't tell" as a miss. |
| `dfa-eq@k (decided)` | The same, but only over tasks where the question could be answered. |
| `exact@k` | Is it the identical string to the reference? |

## Full results — 450 tasks, k=3, 2026-08-12

| Model | dfa-eq@3 | dfa-eq@3 (decided) | exact@3 | undecidable | wrapped |
| --- | ---: | ---: | ---: | ---: | ---: |
| `kimi-k3` | 15.2% | 17.5% | 6.3% | 82 | 18 |
| `claude-opus-5` | 14.0% | 17.0% | 5.4% | 109 | 9 |
| `qwen3.6-max-preview` | 13.8% | 17.4% | 3.8% | 94 | 11 |
| `qwen3.6-plus` | 11.6% | 14.8% | 3.8% | 99 | 9 |
| `deepseek-v4-flash-0731` | 11.3% | 14.3% | 3.3% | 93 | 16 |
| `glm-5.2` | 10.4% | 12.9% | 3.8% | 86 | 18 |
| `claude-sonnet-5` | 10.4% | 13.3% | 3.3% | 97 | 9 |
| `gpt-5.6-terra` | 10.2% | 13.1% | 2.0% | 100 | 11 |
| `gpt-5.6-sol` | 9.6% | 13.6% | 2.0% | 133 | 7 |
| `gpt-5.6-luna` | 9.3% | 12.2% | 2.0% | 113 | 9 |
| `gemini-3.1-flash-lite` | 9.3% | 11.8% | 3.1% | 95 | 16 |

Semantic equivalence tops out at **17.5%** where `pass@3` reaches 47%.
Reproducing the reference *language* is a far harder problem than passing
its examples — which is the case for measuring both.

### Why `dfa-eq` is reported twice

Comparing two regexes as *languages* is solved for most patterns: compile
both to automata, compare the machines. But for patterns using
**backreferences** — `(a)\1`, "match a thing then the same thing again" —
it isn't merely hard, it is **formally undecidable**. No algorithm can
answer it, ever. Not a limitation of this tool; a theorem.

That leaves an honest reporting problem one number cannot solve:

- **`dfa-eq@k`** counts undecidable comparisons as failures. *How much of
  the corpus did we positively verify?* A lower bound that cannot flatter.
- **`dfa-eq@k (decided)`** drops those tasks from the denominator. *Of the
  questions answerable at all, how many did the model get right?*

Publishing only the second is quiet inflation. Publishing only the first
blames the model for a theorem. Both are published, always, with the
undecidable count beside them — **82 to 133 of 450 tasks per model**.

### Why `exact@k` exists

It runs 2.0%–6.3%. That's the point: `[0-9]+` and `[0-9][0-9]*` are the
same language written two ways, and a benchmark scoring by string
comparison would call one wrong. `exact@k` is published to show how badly
that approach misranks everyone, not because it measures anything useful.

## The reference answers contain errors

This is the most important limitation on this page.

`dfa-eq` compares the model against a human-written gold pattern, and some
gold patterns are wrong. Two found by inspection, not by search:

**A literal pipe in a character class.** For *"a very simple ISBN
validation expression"* the reference is `^\d{9}[\d|X]$`. That class
contains digit, **pipe**, and X — someone wrote `|` meaning "or" inside
`[...]`, where it is just a character. `claude-opus-5` wrote `^\d{9}[\dX]$`,
which is what the prompt describes. It is scored as different, and the
witness is `000000000|`.

**A definition disagreement.** For *"Positive integer value."* the
reference `^\d+$` accepts `0`; the model's `^[1-9][0-9]*$` does not. Zero
is not a positive integer.

We have **not** audited how often this occurs. The consequence is
directional and worth stating plainly: **`dfa-eq` is a lower bound on model
correctness.** Some fraction of the gap between `pass@3` and `dfa-eq@3` is
gold-standard error rather than model error.

`usable@k` inherits this, since it counts a proven difference against the
model. `pass@k` and `vulnerable@k` do not — they run the real `re` engine
against real strings and never consult the reference.

## The wrapper rule

Models were asked for a bare pattern in a code block. Some return it
wrapped in host-language string syntax:

```
r'\d+$'      ← what the model said
\d+$         ← what it meant
```

Scored literally, `r'\d+$'` matches the letter `r`, a quote, and so on. It
fails for a reason unrelated to regex ability.

**The rule: one layer of host-language quoting is stripped before scoring**
(`r'…'`, `'…'`, `"…"`, `` `…` ``, `/…/flags`).

It affected **7 to 18 responses per model** out of 1,350 — under 1.4%
everywhere, too small to move any ranking. Every strip is recorded in
`results/sweep/<model>.json` under `wrapped_detail` with before and after,
and the unnormalized score is kept as `metrics_as_sent` so anyone who
disagrees can use the other number without re-running anything.

## Engine limitations

These belong to the scorer, `regexbench` 0.4.0, and apply to every model
equally:

- **`\d` is not `[0-9]`.** It matches every Unicode digit, because that is
  what Python's `re` does and the scorer runs the real `re`. This is the
  single thing most likely to make our numbers differ from another
  published regex eval. It also inflates apparent errors: of 806 answers
  that passed their tests but differed from the reference, **266 differed
  only on Unicode digits** — the model wrote `[0-9]` where the gold wrote
  `\d`, or the reverse.
- **ReDoS screening covers three of five known vulnerability families**
  structurally; the other two are caught only if the empirical pass trips
  them. `vulnerable@k` is therefore a **lower bound**.
- **Lookaround became decidable in `regexbench` 0.4.0.** Earlier versions
  refused it, so these numbers are not comparable to figures produced with
  0.3.0 or earlier.
- **Match semantics are set per corpus.** Re(gEx|DoS)Eval's references pass
  100% of their own tests under "search" semantics and 94% under "full
  match" — picking wrong scores 46 gold answers as failures. Verified by
  scoring every reference against itself before the run.

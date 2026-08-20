# Response to the review

Every number below was recomputed from committed artifacts, and every table
and headline figure in the paper is now generated from them — `make analysis
&& make tables && make docs` rebuilds the lot, and continuous integration
fails on any drift. Where our recomputation disagreed with the review, our
figure and the command that produces it are given.

Three of the corrections changed a number we had published. One of them,
which the review did not raise, changed the ordering of the primary table.

---

## The two you said you would insist on

### 1. The anchored comparison in Table 5 is now matched

You were right that the model row was the unrestricted rate while every other
row in the block was anchoring-restricted, and right that it carried neither
`n` nor an interval. `runner/anchored_models.py` computes the models under the
identical rule — keep only patterns matching `^...$`, screen them with the same
`regexbench.safety.screen` — after first reproducing Table 4 bit-exactly as a
control.

| anchored only | n | vulnerable |
| --- | ---: | ---: |
| RegexLib, published for reuse | 1,684 | 20.1% ± 1.9 |
| Stack Overflow posts | 4,000 | 17.3% ± 1.2 |
| Re(gEx\|DoS)Eval gold answers | 538 | 13.4% ± 2.9 |
| **This work, 11 models pooled** | **3,613** | **9.8% ± 1.0** |
| Production code | 4,000 | 8.9% ± 0.9 |

The thesis survives: 9.8% against 8.9% is *z* = 1.27, *p* = 0.20, while both
sit far below every population written to be read. The correction moves the
models **toward** the answer key rather than away, and §4.4.1 now says so.

Two stricter matchings are available to us and not to the wild populations,
because we know which task each model pattern answers. Restricting to the 330
tasks whose reference is anchored: models 10.6%, reference 13.9%. Requiring
both an anchored output and an anchored task: 11.4% against 13.9%, at which
point the model-versus-reference difference stops resolving. That is the
honest ceiling on the reference comparison and it is now in the paper. It does
not touch the production comparison, which is a population-level restriction
applied identically on both sides.

### 2. The 7.4% / 16.5% pair means one definite thing

It is a rate over **generations**, not tasks: 390 of the 5,269 samples that
satisfied every test were screened unsafe, so 7.40%. That makes it an @1
quantity, which is what Table 8 claimed and could not previously be checked.
The task-level figure is 144 of 2,051 and is now also stated. Both regenerate
with `make persample`.

The count of **135 does not reproduce from our released data** — not at 390
(per sample), 144 (`pass@3 ∧ ¬C&S@3`), 180 (≥1 correct-and-vulnerable sample)
or 196 (`pass@3 ∧ vuln@3`). We have removed it rather than reinterpreted it,
and said in the text that we could not reproduce it.

---

## The other major points

**ReDoS screen calibration (2).** Three separate problems, each now measured
rather than caveated.

*The compile filter is not uniform.* It drops 5.0% of the production pool
(26,900 of 537,804) against 11.4% of Stack Overflow and 10.2% of RegexLib, and
within production from 7.7% (cpan) to 0.3% (pypi). It is enriched for anchored
shapes — 23.7% of what it drops is anchored against 17.2% of what it keeps. We
had assumed this biased in our favour; it does not obviously do so, since the
read-to-be-read populations lose more, and the paper now says that too.

*Engines that cannot backtrack.* godoc and crates.io (24,128 patterns, 4.5% of
the pool) target RE2 and the Rust `regex` crate. They are broken out.

*Does either produce the result?* `runner/dialect.py` translates what can be
translated without guessing (`\A`→`^`, `\z`→`\Z`, `\Q…\E`, named groups,
`\x{…}`) and declines what cannot (`\G`, `\p{…}`), recovering 17,151 of the
26,900. Anchored production then reads:

| variant | anchored vulnerable |
| --- | ---: |
| as published | 8.9% ± 0.9 |
| dialect-normalised | 9.1% ± 0.9 |
| backtracking-engine registries only | 8.3% ± 0.9 |
| both | 8.2% ± 0.8 |

The whole range is 8.2–9.1%, inside the interval on any one of them, and the
models remain indistinguishable from every variant. The defects are real and
they are not what produces the result.

*Sensitivity, per population.* `runner/screen_calibration.py` pairs an
independent detector — `weideman-RegexStaticAnalysis`, from Davis et al.'s own
artifact — with a dynamic oracle: we take the detector's exploit string, build
it at growing pump counts, and time CPython's matcher on it. Confirmation is a
measured hang or a fitted super-linear growth exponent, not a second static
opinion.

| population | caught/confirmed | recall | 95% CI |
| --- | ---: | ---: | ---: |
| Stack Overflow | 25/27 | 92.6% | [77, 98] |
| RegexLib | 33/36 | 91.7% | [78, 97] |
| Re(gEx\|DoS)Eval gold | 19/22 | 86.4% | [67, 95] |
| Production code | 16/20 | 80.0% | [58, 92] |
| NL-RX-Synth | 16/21 | 76.2% | [55, 89] |
| Model outputs | 11/15 | 73.3% | [48, 89] |
| KB13 | 2/3 | 66.7% | [21, 94] |

The intervals overlap almost everywhere, so this does not resolve a fine
ordering of sensitivities and we do not claim one. It resolves the direction,
which is what your objection turned on. For differential blindness to
manufacture the result, recall would have to be **lower** in production code
than in showcase validators. It is the other way round: the two populations
where the screen is most sensitive are RegexLib and Stack Overflow — the two
with the highest measured vulnerability — while production sits at 80.0%.

Dividing each anchored rate by its recall turns 20.1 / 17.3 / 13.4 / 9.8 /
8.9% into 21.9 / 18.7 / 15.5 / 13.4 / 11.1%. Every rate rises, because the
screen is a lower bound everywhere; the ordering is unchanged; the
read-against-run gap does not close. We do not put those in a table — recall
is relative to one detector's findings and the counts are small — but the
check is the one a reader should want.

Two limitations are stated with it. The detector could not analyse between 46
and 110 of each 240-pattern sample, so ground truth covers the patterns two
tools can both reason about. And screen/detector agreement runs 53–74%, far
below either one's recall, because the detector flags plenty that does not
actually blow up under CPython — which is why a timing measurement, not a
second opinion, is the arbiter here.

Building that also caught us repeating the mistake we criticise: the oracle
initially labelled every timeout exponential, and a quadratic pattern reaching
the timeout at 1,600 characters was recorded as exponential. A hang now counts
as exponential only on an input short enough that a quadratic matcher would
finish instantly.

**Clustered intervals (3).** The human baseline now uses an exact McNemar test
on the paired tasks. "Every model is safer than the reference set" becomes
**eight of eleven**; the three that do not separate — `kimi-k3` (*p* = 0.14),
`claude-opus-5` (0.065), `glm-5.2` (0.058) — are the three most vulnerable
models, which is what one would expect and is not what the point estimates
said. Table 1 carries a paired-bootstrap interval on `usable@3`, bootstrapped
over each model's own scored tasks so it brackets the score beside it.

**NL-RX-Synth (4).** It is the clearest instance of our own mechanism, not an
embarrassment. All 2,057 of its vulnerable targets come from the structural
pass and none from the empirical one: 994 nested quantifier, 891 adjacent
quantifiers over overlapping sets, 172 overlapping alternation. The generating
grammar composes `.*`, `(…)*` and `(…){n,}` over overlapping classes, and
those compositions are the vulnerable shapes. It is the population with the
least exposure to execution of any we measured and the most vulnerable.

This connects to §4.6, as you suspected. On the correct patterns, the shape
shares invert between corpora: 236 nested against 154 adjacent on
Re(gEx|DoS)Eval, 202 against 355 on StructuredRegex. The nested count barely
moves while the adjacent count more than doubles, so the extra vulnerability
is entirely the polynomial family — which is what a grammar over concatenation
produces.

**The audit (5).** The rule is recoverable from the committed sample and is now
stated: *the first 14 in seed order whose witness is ASCII*. Consequently none
of the 14 is among the 19 non-ASCII cases, so the combination does not
double-discount; it now reads `(41/60) × (3/14) = 14.6%`. The verdict-label
mapping is stated too.

**The `undec` asymmetry (6).** Real, and larger than the correlation test
shows. Correlating undec count against `usable@3` returns nothing (Pearson
−0.13) because undec credit and equivalence skill push the composite in
opposite directions. Decomposing instead: **471 of 975 usable task-credits
(48.3%)** rest on a verdict the engine could not decide, the share tracks undec
count at *r* = +0.82, and removing the credit drops `gpt-5.6-sol` seven places.
It has its own section now, as a third independent reason to distrust the
composite.

---

## The arithmetic list

All ten confirmed. Two came out differently than described.

| # | Resolution |
| --- | --- |
| Failure taxonomy 54 vs 44 | The missing 10 are responses the API returned as successful that hit the 200-token cap after an opening code fence, yielding no pattern: 7 opus, 2 kimi, 1 luna. A fifth row, and the table now totals. |
| opus coverage | **444** is right; 445 was wrong in four places. |
| `vuln.\|correct` column | Per-sample while the rest of the row is @3, exactly as you inferred. Labelled in the caption. |
| 7.4% denominator | See above. |
| Population sizes | Two different denominators. NL-RX-Synth: 10,000 rows → 9,648 distinct → 5,840 screened. KB13: 824 → 732 → 532. The 3,948 and 212 were DSL counts over raw rows. |
| StructuredRegex coverage | 182 blocked − 98 recovered = 84 hard refusals, **plus 25 truncated responses** (same mode as the taxonomy above). 84 + 25 = 109 = 622 − 513. |
| Table 9 caption | Cost per *request*; the column header was wrong too. |
| §3.2 "100%" | 761 of 762. The exception does not mismatch — it **times out** at the scorer's one-second limit on a negative example, and the safety screen independently flags it exponential. The one reference that fails its own tests fails because it is ReDoS-vulnerable. It is now a paragraph. |
| Table 2 caption | States the restricted denominator. |
| §6 cross-reference | Fixed; §3.5 now carries a label. |

## The smaller points

Intervals are on Tables 1 and 7 and the human baseline carries McNemar *p*.
The 87% is stated as the lower bound the decomposition's order makes it — a
sentence, as you said. The differential retry effort for `claude-opus-5` on
StructuredRegex is stated beside the filter-bias check. The survivorship
alternative is named, with what we can and cannot test: the artifact carries
registry and module counts but no maintenance history, so a clean
"unmaintained packages" test is not available to us and we say so rather than
implying we ran it. §4.5 now tests the difficulty-ceiling hypothesis instead
of listing it, and it does not survive: StructuredRegex's correct patterns are
longer and carry more quantifiers than ours while being twice as vulnerable.
There is a figure.

---

## One thing you did not find

Chasing a 1.3-point discrepancy between two of our own tables turned up a
defect in the scorer. `pass_at_k` early-returns 1.0 when `n − c < k`, which is
sound only for `n ≥ k`; a task that lost samples to a refusal or a spending
limit satisfies it unconditionally and scored a full 1.0 on every metric
regardless of outcome — `pass_at_k(1, 0, 3) == 1`.

This is the real cause of the Table 1 / Table 3 disagreement you noticed as
item 9. Table 3 excluded short-sample tasks and was right; Table 1 credited
them and was not. It inflated exactly the two models that lost the most
samples, which were the two at the top of the table:

| model | short tasks | `pass@3` | `usable@3` |
| --- | ---: | ---: | ---: |
| `kimi-k3` | 6 | 47.2 → 46.5 | 24.8 → **23.8** |
| `claude-opus-5` | 12 | 47.5 → 46.1 | 23.0 → **20.8** |
| `gpt-5.6-sol` | 1 | 42.2 → 42.1 | 21.1 → 20.9 |
| `gpt-5.6-luna` | 1 | 39.3 → 39.2 | 18.7 → 18.5 |

`claude-opus-5` moves from second to fourth, and `kimi-k3` rather than
`claude-opus-5` has the highest `pass@3`. Rescoring the four affected models
reproduces Table 3's independently computed figures exactly, and rescoring the
seven unaffected ones confirms the change is a no-op where no samples were
lost. No claim turns on it — we publish no ranking — but Table 1 is ordered by
the affected column, and it is now in the hazards appendix.

The cost comparison also inverts, and makes its point better: the cheapest
model and the most expensive now differ by 1.1 points **in the cheaper one's
favour**, across a 98× price range.

## On the process point

The length of the arithmetic list was the real signal, and you said so. Five
of the paper's eleven tables were hand-maintained LaTeX, one generated table
read an intermediate from `/tmp` that no clone has, the per-sample counts
carrying the reference-independent headline had nothing in the repository able
to rebuild them, and the cross-population script hard-coded an absolute path
from a machine that no longer exists. Every discrepancy you found lived in one
of those.

So the fix is mechanical rather than editorial. `make_tables.py` emits every
table and every headline number the prose states; `render_docs.py` does the
same for the README and appendix; `per_sample.py --check` verifies the
committed counts rebuild exactly (they do); corpus acquisition is pinned by
commit in `make setup-corpora`; and CI rebuilds and diffs. It is now a
recommendation in §7, because we do not think we are the only ones with this
failure mode.

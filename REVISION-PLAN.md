# Revision plan — expert review of *Passing Is Not Shipping*

Status: planning document. Every number below was recomputed from committed
artifacts in this repository (`make setup` + the scripts named), not read off
the paper. Where the reviewer's arithmetic and ours disagree, our figure and
the command that produced it are given.

---

## Part 1 — Validation of the reviewer's points

### Major

#### 1. Table 5's anchored model row is unmatched — **CONFIRMED, and the fix is computed**

`tab_crosscorpus.tex` places `This work, 11 models pooled — 9.0%` inside the
anchored block. That 9.0% is the pooled per-sample rate over *all* model
outputs (Table 4), while every other row in the block is restricted to
anchored `^...$` patterns. The comparison is unmatched, exactly as claimed,
and the row carries no `n` and no interval.

We recomputed the models under the identical restriction (first sample per
task per model, keep only outputs matching `^\^.*\$$`, screen with the same
`regexbench.safety.screen(empirical=True)`):

| population (anchored only) | n | vulnerable |
| --- | ---: | ---: |
| RegexLib, published for reuse | 1,684 | 20.1% ± 1.9 |
| Stack Overflow posts | 4,000 | 17.3% ± 1.2 |
| Re(gEx\|DoS)Eval gold answers | 538 | 13.4% ± 2.9 |
| **This work, 11 models pooled** | **3,615** | **9.8% ± 1.0** |
| Production code | 4,000 | 8.9% ± 0.9 |

**The thesis survives the correction.** Matched, the models are at 9.8% and
production code at 8.9% — a 0.9 pp difference, two-proportion z ≈ 1.3,
not distinguishable — while the gold answers stay 3.6 pp above both and the
read-only populations stay far above. The correction moves the models
slightly *toward* the answer key and away from production code, which is the
direction that costs us something, and it must be reported as such.

Two robustness variants, both computed:

* **Task-matched** (the 330 of 450 tasks whose *gold* is anchored, all model
  outputs on them): gold 13.9% (n = 330), models 10.6% (n = 3,627).
* **Doubly restricted** (gold-anchored task *and* anchored model output):
  models 11.4% (n = 2,864) against gold 13.9%. Under this strictest matching
  the model/gold difference is no longer resolvable (CIs [10.2, 12.6] and
  [10.2, 17.6]).

The doubly-restricted variant is the honest ceiling on how strong the
"models are safer than the answer key" claim can be made, and it belongs in
the paper alongside the headline row.

Reproduction: `runner/anchored_models.py` (to be added; prototype in the
session scratchpad reproduces Table 4 bit-exactly first, as a control).

#### 2. The ReDoS screen is never calibrated, and dialect/engine validity is unexamined — **CONFIRMED, and worse than stated**

Three separate problems, two of which the reviewer named:

* **No sensitivity estimate.** True. `screen()` combines a structural pass
  over three of Siddiq et al.'s five families with an empirical pass that
  probes at lengths 14/20/26 under a 0.5 s timeout. No FP/FN numbers exist
  anywhere in the repository.

* **Silent compile-drop, and it is differential.** `cross_corpus_redos.py`
  filters production / Stack Overflow / RegexLib through `re.compile()` and
  drops what fails, with no count reported. Recomputed:
  **26,900 of 537,806 production patterns (5.0%) are dropped**, and the drop
  rate is far from uniform across registries — cpan 7.7%, rubygems 7.5%,
  packagist 3.7%, maven 5.3%, npm 0.8%, pypi 0.3%. The dropped patterns are
  overwhelmingly Perl/Ruby syntax Python rejects (`\A...\z`, `\G`,
  `\Q...\E`, `\u{...}`), i.e. disproportionately the *anchored, validator*
  shapes that the anchored block is built on. This is a real bias in the
  direction that produces our result and it is currently invisible.

* **Engines that cannot backtrack.** The production corpus spans eight
  registries; **godoc (22,104 patterns) and crates.io (2,024)** — 4.5% of the
  pool — target RE2 and the Rust `regex` crate, both linear-time by
  construction, where catastrophic backtracking is impossible. Screening them
  as if they ran under a backtracking engine is a category error, small in
  magnitude but trivially avoidable: the record carries
  `useCount_registry_to_nModules`.

* **(Not in the review) The exponential/polynomial split is threshold-assigned,
  not measured.** In `_empirical`, a pattern is labelled EXPONENTIAL if it
  times out at probe length 14 and POLYNOMIAL if it survives to 20 or 26.
  That is a proxy for growth order, not a measurement of it. §4.4.2's
  comparison against Siddiq et al.'s polynomial-skew finding rests on this
  split and currently overstates what the screen can support.

* **(Not in the review) `screen()` returns SAFE for patterns that do not
  compile.** Harmless given the pre-filter, but it means any non-compiling
  pattern reaching the screen is counted safe rather than excluded.

#### 3. Independent binomial intervals on clustered data — **CONFIRMED**

Tables 4 and 5 pool 4,941 patterns that are eleven models answering the same
450 tasks and interval them as independent Bernoulli draws. The paper has
the paired machinery (`runner/paired_stats.py`, §5.2, Recommendation 3) and
does not apply it to its own human-baseline result. McNemar is directly
available: gold pattern and model pattern are paired on task.

`kimi-k3` 10.7% vs reference 13.6% at n ≈ 450 is nowhere near resolvable
under independent intervals, and "every model is safer than the reference
set" is currently asserted from an eleven-way ordering with no test at all.

#### 4. NL-RX-Synth at 35.2% is undiscussed — **CONFIRMED, and it is an asset, not a liability**

We screened all 5,840 dialect-clean NL-RX-Synth targets and broke the
verdicts down by reason. **Every one of the 2,057 vulnerable patterns comes
from the structural pass; none come from the empirical pass:**

| reason | count |
| --- | ---: |
| SAFE — no known-vulnerable structure | 3,783 |
| EXPONENTIAL — quantifier wraps a quantified group | 994 |
| POLYNOMIAL — adjacent quantifiers over overlapping sets | 891 |
| EXPONENTIAL — quantifier wraps overlapping alternation | 172 |

Representative targets: `.*(.*)([a-z]).*`, `(dog.*[0-9].*)+`,
`((dog)|(..*[AEIOUaeiou].*)){4,}`. The generating grammar composes `.*`,
`(...)*` and `(...){n,}` freely over overlapping character classes, which
*is* the nested-quantifier and adjacent-quantifier shape. The 35.2% is not
the screen behaving oddly; it is a grammar that manufactures ReDoS shapes at
scale because nothing downstream of it ever runs the output.

That makes NL-RX-Synth the purest instance of the paper's own mechanism, and
it connects directly to §4.6: StructuredRegex is also grammar-built over
repetition/optionality/concatenation, and is where `vuln|correct` doubles to
16.5%. The paper should make that connection instead of leaving the row
unexplained.

#### 5. The audit's 15% is underspecified — **CONFIRMED as a writing gap; the arithmetic itself is sound**

The selection rule is recoverable from `results/sweep/disagreements.json`.
The 14 adjudicated cases are at indices 1, 2, 4, 5, 6, 7, 9, 10, 11, 12, 13,
14, 15, 18 in seed order. Indices 0, 3, 8, 16, 17 are exactly the non-ASCII
witnesses in that prefix. So:

> **the first 14 cases in seed order whose witness is ASCII.**

Consequently **none of the 14 are among the 19 non-ASCII cases**, and the
`21% × (1 − 0.32)` combination is valid — there is no double-discounting.
It reads more transparently as `(41/60) × (3/14) = 14.6%`. Both need saying;
neither is currently said.

The verdict labels also need a stated mapping: `model_right` (5) → reference
incorrect, `ambiguous` (6) → description underspecifies, `gold_right` (3) →
model incorrect. That mapping is correct as printed in Table 10 but is
nowhere stated.

#### 6. The `undec` asymmetry — **CONFIRMED as a mechanism; the predicted correlation is absent**

`dfa-eq` counts UNDECIDABLE as failure; `usable`'s third conjunct excludes
only proven DIFFERENT, so undecidability is scored as a pass. A model that
reaches for backreferences is mechanically credited. That much is exactly as
described and deserves naming.

The predicted correlation does not appear. Across the eleven models:

| undec vs | Pearson | Spearman |
| --- | ---: | ---: |
| `usable@3` | −0.03 | −0.14 |
| `pass@3` | −0.07 | −0.13 |
| `dfa-eq@3` | −0.42 | −0.46 |

If anything the sign is negative, and `gpt-5.6-sol` has the most undec (133)
while sitting fourth. The between-model correlation is a weak test at n = 11
and confounded by overall model quality, so the paper should report the
*within-model* quantity instead: what share of each model's `usable@3` rests
on a non-EQUIVALENT verdict. That computation is in flight
(`runner/undec_credit.py`) and will be reported whichever way it lands.

Reporting a null here is worth more than reporting nothing: it says the
perverse incentive is real in the metric's definition but is not, on this
data, moving the composite.

### Arithmetic and consistency — every item checked

| # | Reviewer's claim | Verdict | Our finding |
| --- | --- | --- | --- |
| 1 | Failure taxonomy 54 vs 44 | **Confirmed** | The missing 10 are responses with `status=ok` that returned an unclosed or empty code fence and no extractable pattern — 7 `claude-opus-5`, 2 `kimi-k3`, 1 `gpt-5.6-luna`, all truncation at the 200-token cap. A fifth row, not a rounding error. |
| 2 | opus coverage 444 vs 445 | **Confirmed; 444 is right** | 444 tasks have ≥1 scored sample. `445` is wrong in §6, `METHODOLOGY.md:276`, `README.md:169`, `FINDINGS.md:684`. |
| 3 | `vuln.\|correct` is per-sample, rest of Table 2 is @3 | **Confirmed exactly** | `make_tables.py` computes it as `Σ pass − Σ correct_secure` over *per-sample* counts. gpt-5.6-sol: 502 correct samples, 474 correct-and-secure → 5.6%. Label the column. |
| 4 | 7.4% has an ambiguous denominator | **Confirmed, and the numerator is wrong** | 7.4% = **390 of 5,269 correct samples** (per-sample, i.e. @1) — so Table 8's "like for like at @1" is right. But **135 is not reproducible from the released data.** Candidate counts: 390 (per-sample), 144 (`pass@3 ∧ ¬C&S@3`), 180 (≥1 correct-and-vulnerable sample), 196 (`pass@3 ∧ vuln@3`). None is 135. The sentence must be rewritten around 390/5,269, not merely clarified. |
| 5 | Population sizes don't match the exclusions | **Confirmed** | The two numbers are on different denominators. NL-RX-Synth: 10,000 raw → 9,648 unique → 3,808 DSL-excluded → **5,840**. KB13: 824 raw → 732 unique → 200 excluded → **532**. The `3,948` and `212` are DSL counts over *raw* lines, before de-duplication. |
| 6 | StructuredRegex coverage doesn't close | **Confirmed; 25 recovered** | 182 blocked − 98 recovered = 84 hard-core refusals, **plus 25 responses that returned `ok` with an empty fence** (same truncation mode as item 1). 84 + 25 = 109 = 622 − 513. The 25 are undocumented. |
| 7 | Table 9 caption is wrong | **Confirmed** | `cost_usd_per_task` = total ÷ 1,350 = cost per *request*. opus: 2514.2 × 10⁻⁶ × 1,350 = \$3.39 = the reported total. Both the caption and the column header say "task". |
| 8 | §3.2 "100%" vs §5.1 "449 of 450" | **Confirmed, with a better story** | Over all 762 references, 761 satisfy their own tests. The single exception, `regexeval/1660` (`^((\.)?([a-zA-Z0-9_-]?)(\.)?([a-zA-Z0-9_-]?)(\.)?)+$`), does **not** mismatch — it *times out* at the scorer's 1 s limit on the negative example `.....444fef454#`, which the scorer counts as a false positive. The safety screen independently flags the same pattern EXPONENTIAL. The one reference that fails its own tests fails because it is ReDoS-vulnerable. That is a paragraph, not an erratum. |
| 9 | Table 2 caption omits the restricted denominator | **Confirmed** | Tables 2 and 3 exclude tasks with `n < 3` samples (6 for kimi), which is why kimi is 46.5 there and 47.2 in Table 1. |
| 10 | §6 "Sampling control" cross-ref | **Confirmed** | Points at `sec:metrics` (§3.4). Temperature is §3.5, which carries no label. |

### Smaller things — all confirmed

* No CIs in Tables 1, 2, 3, 4, 7. The bootstrap exists and is unused there.
* The decomposition subtracts safety first, so safety absorbs the whole
  unsafe-correct set including patterns that also fail equivalence, and
  equivalence keeps only its unique share. 87% is therefore a **lower bound**
  on the equivalence term's contribution under any order-symmetric
  attribution. One sentence, and it removes the order-dependence objection.
  We will also compute the reverse-order decomposition to state the bound
  numerically rather than by argument.
* StructuredRegex retries were differential effort — only `claude-opus-5` got
  five rounds. Must be stated next to the filter-bias check.
* Survivorship has a competing explanation (`safe-regex`-style lint prevented
  the bad pattern, rather than execution repaired it). Partly separable; see
  the plan below for what the LinguaFranca artifact can and cannot support.
* §4.5's three unseparated explanations. A length- and construct-count-matched
  comparison of the correct subsets on both corpora discriminates hypotheses
  1 and 3 and is computable offline.
* No figures. The six-population ordering wants a plot.

---

## Part 2 — Additional findings not in the review

These are the mechanical cause of the reviewer's arithmetic list, and fixing
them is what makes "one careful pass from a single source of truth" stick.

1. **`paper/make_tables.py` reads `/tmp/vulntypes.json`** — a scratch file
   that is not in the repository and no longer exists. `tab_vuln.tex`
   therefore cannot be regenerated from a clean checkout, and its human-
   reference row is a hard-coded string literal in the script.
2. **`tab_crosscorpus.tex`, `tab_sr_common.tex` and `tab_sr_compare.tex` are
   not generated at all.** They are hand-maintained LaTeX. Every discrepancy
   in the reviewer's list lives in a hand-maintained table or a hand-written
   sentence.
3. **`runner/cross_corpus_redos.py` hard-codes an absolute scratch path** from
   a dead session (`/tmp/claude-0/.../4f381924-.../scratchpad`). The script
   cannot run anywhere. Corpus acquisition needs to move into `make setup`.
4. The claim in §7 that scoring "recomputes offline from committed data with
   no API access" is true for the main run and false for Tables 4, 5, 7 and 8.

---

## Part 3 — Work plan

Ordered by what the reviewer said they would insist on, then by dependency.

### Phase A — single source of truth (blocks everything else)

* **A1.** Move corpus acquisition (`RegexEval.json`, deep-regex, LinguaFranca
  FSE19) into `make setup` with pinned commits and checksums; drop the
  hard-coded scratch path from `cross_corpus_redos.py`.
* **A2.** Make `make_tables.py` generate *every* table in the paper from
  committed JSON. Delete the `/tmp/vulntypes.json` dependency and the
  hard-coded reference row. Add `make check-tables` to CI so a stale table
  fails the build.
* **A3.** Commit the intermediate JSON that each table reads
  (`results/vuln_by_type.json`, `results/cross_corpus_redos.json` refreshed,
  `results/structuredregex_scores.json` already committed).

### Phase B — the two the reviewer will insist on

* **B1 (Major 1).** `runner/anchored_models.py`: reproduce Table 4 as a
  control, then emit anchored model rates with `n` and CI, plus both
  robustness variants. Rewrite the Table 5 anchored block and the §4.4.1
  block quote around **9.8% ± 1.0 (n = 3,615)** vs production 8.9% ± 0.9.
  State the direction of the correction explicitly, and add the
  doubly-restricted 11.4% vs 13.9% as the honest ceiling.
* **B2 (Arithmetic 4).** Replace the "135 model-task pairs" sentence with
  **390 of 5,269 correct samples (7.40%)**, state the denominator as
  per-sample in §4.2, in Table 2's caption, and in Table 8, and add the
  @3-level count (144 of 2,051 tasks) so both readings are on the page.
  Propagate to `ARTICLE.md`, `FINDINGS.md`, `README.md`.

### Phase C — screen validity (Major 2)

* **C1.** Report the compile-drop explicitly: counts and rates per population
  and per registry, in Table 5's notes and §4.4.1.
* **C2.** Add a dialect-normalisation layer (`\A`→`^`, `\z`/`\Z`→`$`,
  `\Q...\E`→escape, `\h`, `\R`) and report the production rate with and
  without it, so the reader can see whether recovering the dropped 5% moves
  the number. If it moves it materially, the normalised figure becomes the
  headline.
* **C3.** Report the production rate restricted to backtracking-engine
  registries (excluding godoc and crates.io) as a robustness row.
* **C4.** Calibrate. Preferred: build the `vuln-regex-detector` ensemble that
  ships inside the LinguaFranca artifact (rxxr2, RegexStaticAnalysis,
  RegexCheck, ReScue) and report FP/FN of our screen against it on a
  stratified sample drawn across all six populations, so sensitivity is
  reported *per population*, which is what the cross-population comparison
  actually needs. Fallback if the ensemble will not build: dynamic ground
  truth — for every SAFE verdict in the sample, generate attack strings and
  fit the match-time growth curve; for every vulnerable verdict, confirm a
  witness that exhibits super-linear time. Either way the deliverable is a
  per-population sensitivity table, not a single number.
* **C5.** Downgrade the exponential/polynomial split. Either replace the
  threshold rule with a measured growth-order fit, or state plainly that the
  split is threshold-assigned and weaken §4.4.2's comparison to Siddiq et al.
  accordingly.

### Phase D — inference (Major 3, smaller item 1)

* **D1.** McNemar (exact binomial on discordant pairs) for each model against
  the reference set on the 450 paired tasks, plus a pooled test. Report in
  Table 4. Replace "every model is safer than the reference set" with
  whatever the test supports.
* **D2.** Attach paired-bootstrap CIs, clustered on task, to Tables 1, 2, 3,
  4 and 7.
* **D3.** For the cross-population comparisons in Table 5, keep binomial
  intervals (those populations are genuinely unpaired) but say so, and use a
  two-proportion test for the model/production comparison rather than eyeball
  overlap.

### Phase E — the substantive additions

* **E1 (Major 4).** Write NL-RX-Synth into §4.4.1 with the reason breakdown,
  and connect it to §4.6: grammar-generated targets manufacture the shapes,
  which is why StructuredRegex doubles. This is a strengthening, not a patch.
* **E2 (Major 5).** State the selection rule ("first 14 in seed order with an
  ASCII witness"), state that none of the 14 are among the 19 non-ASCII
  cases, and give the combination as `(41/60) × (3/14) = 14.6%`. State the
  verdict-label mapping.
* **E3 (Major 6).** Name the asymmetry, report the null between-model
  correlation, and report the within-model undec-supported share of
  `usable@3`.
* **E4 (smaller).** One paragraph in §4.2: the decomposition's order makes 87%
  a lower bound, with the reverse-order number to fix the interval.
* **E5 (smaller).** §4.5: length- and construct-count-matched comparison of
  the correct subsets across the two corpora, to discriminate the
  attack-surface hypothesis from the difficulty-ceiling hypothesis.
* **E6 (smaller).** §4.4.1: state the survivorship alternative explicitly.
  What the LinguaFranca artifact supports is a popularity stratification
  (`useCount_registry_to_nModules`); it carries no maintenance or commit
  history, so a clean "unmaintained packages" test is not available offline.
  Report the popularity stratification and state the limitation rather than
  implying the test was run.
* **E7 (smaller).** Note the differential retry effort for `claude-opus-5` on
  StructuredRegex next to the filter-bias check.
* **E8.** One figure: the six-population ordering, unanchored and anchored,
  with intervals.

### Phase F — the clerical pass

Single sweep, from the regenerated tables, fixing: the failure taxonomy
(add the truncation row, 44 → 54); opus coverage 445 → 444; Table 2's caption
(restricted denominator, per-sample column); Table 9's caption and header
(per request, not per task); §3.2's "100%" → 761 of 762 with the timeout
explanation; the NL-RX/KB13 exclusion sentence; the StructuredRegex 84 + 25
reconciliation; the §6 cross-reference. Then propagate every changed number
to `ARTICLE.md`, `FINDINGS.md`, `README.md`, `METHODOLOGY.md`, `APPENDIX.md`
and `docs/preview.html`.

### What changes a conclusion

Only B1, and it survives: matched, models 9.8% and production 8.9%, still
indistinguishable, still well below every read-to-be-read population. C4
could in principle overturn the ordering if sensitivity turns out to be
strongly population-dependent; that is the one open risk in the plan and it
is the reason C4 is not optional.

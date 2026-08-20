# regexeval-2026 — handoff validation & implementation plan

Written 2026-08-07, against [docs/HANDOFF.md](docs/HANDOFF.md) (dated
2026-08-02). Every claim in the handoff was checked from this environment
before this plan was written. Section 1 is what checked out, what changed,
and what is wrong; section 2 is the plan; section 3 is what is needed from
a human before Phase 1 can run.

**Update, 2026-08-11:** `OPENROUTER_KEY` is set and network access to
`openrouter.ai` is confirmed working — §3 blockers 1 and 2 are resolved,
details in §0. `regexbench` also moved to **0.4.0** the same week (not yet
on PyPI — installed from GitHub `main`); §0 covers what changed and how it
updates the rest of this plan. Section numbers below are otherwise
unchanged from the original.

---

## 0. Update — access confirmed, regexbench 0.4.0

### 0.1 Access (§3 blockers 1–2, resolved)

- `openrouter.ai` is now reachable from this environment: `GET
  /api/v1/models` → 200, 405 models listed.
- `OPENROUTER_KEY` is set and valid: `GET /api/v1/auth/key` → 200,
  `is_free_tier: false`, **`limit: 5`** (i.e. a **$5** hard cap on this
  key), `expires_at: 2026-09-10`. Two things this changes in Phase 1: the
  cost extrapolation in step 4 is now checked against a real $5 ceiling
  before any sweep is approved, not just estimated in the abstract; and the
  runner needs to treat a key-limit rejection the same as a 429 (back off,
  log, do not silently drop the row) rather than assuming only rate limits
  can fail a request. §3 blocker 3 ("confirm ≥$10 lifetime credit") is
  answered too, in the opposite direction — this key is **capped at $5**,
  which is a hard constraint on Phase 2's scale, not just a data point.

### 0.2 `regexbench` 0.4.0 (2026-08-10)

> **Superseded 2026-08-19.** 0.4.0 is now on PyPI, so the Makefile pins
> `regexbench==0.4.0` rather than the commit. Verified by re-scoring the
> committed predictions against the PyPI build: every metric is
> byte-identical. The commit is still recorded in every result file.
> The reasoning below was correct when written and is kept as written.

Not yet published to PyPI (still shows 0.3.0 as latest there) — installed
from GitHub at commit `412eaa95a3f512b5a7bd3d8de2ae70c003d6a206`
(`main`, 2026-08-11). **This exact commit, not a version string, is what
must be pinned and recorded** until a PyPI release exists — `pip install
regexbench==0.4.0` will silently resolve to nothing or a future differently
-pinned commit; use `pip install
"git+https://github.com/foothills-labs/regexbench.git@412eaa95a3f512b5a7bd3d8de2ae70c003d6a206"`
verbatim in the runner's setup and in METHODOLOGY.md.

What changed, verified against the live package:

- **Lookaround is now decidable, not `UNSUPPORTED`.** `(?=…)`, `(?!…)`, and
  fixed-width lookbehinds build into automata (constraint machines with
  marker symbols) instead of refusing. Confirmed: `equivalent(r"(?=a)ab",
  "ab").verdict` → `EQUIVALENT` (previously would have been
  `UNSUPPORTED`). This directly changes the numbers from the handoff and
  from 0.3.0: Re(gEx|DoS)Eval's README figure of "5.6% lookaround,
  `UNSUPPORTED`" no longer applies at 0.4.0 — that slice is now decided,
  which raises the *denominator* of `dfa-eq@k (decided)` and should move
  its value. Backreferences remain the one genuinely `UNDECIDABLE`
  construct; that part of the methodology is unchanged.
- **14 wrong-verdict fixes** from stricter AST-walker validation (unhandled
  node types now fail loudly instead of silently) and syntax-driven
  differential fuzzing derived from a declared `_syntax.SYNTAX` list (56
  constructs) rather than a hand-maintained one that previously missed
  lookaround entirely.
- **New: `crosscheck()`** — string-by-string differential verification
  against Python's own `re`. Worth using as an extra control in Phase 0:
  run it over the committed controls (and optionally a sample of scored
  predictions) as a second, independent check that the equivalence engine
  agrees with `re` on the same inputs, before trusting a sweep's numbers.
- **New: `load_linguafranca()`** — loads the LinguaFranca FSE'19 corpus
  (MIT-licensed, ~538k PyPI-sourced regexes, ~495k from Stack Overflow,
  ~3.8k from RegExLib). **Not a candidate task set for this leaderboard**:
  each entry is a bare pattern with no natural-language prompt and no
  positive/negative examples, so there is nothing for a model to generate
  from. It's a validation corpus for `regexbench` itself (the changelog
  credits it with catching 6 engine bugs), not a benchmark corpus — noting
  it here so it isn't mistaken for a fourth task-set option in §2.

Re-validated the smoke test from §1.4 under 0.4.0 on the full 762-task
corpus, not just 25/50 tasks:

```
control-good (all 762 references, --use-reference equivalent)
  pass@1 99.9%  dfa-eq@1 100.0%  dfa-eq@1 (decided) 100.0%
  exact@1 100.0%  usable@1 86.9%  vulnerable@1 13.1%

control-bad ("z{5}" against all 762 references)
  pass@1/dfa-eq@1/exact@1/usable@1 all 0.0%, vulnerable@1 0.0%
  5 undecidable (backreference references — correctly excluded from "decided")

control-vuln ("(a+)+b" against 20 references)
  pass@1/dfa-eq@1/exact@1/usable@1 all 0.0%, vulnerable@1 100.0%
```

Matches the README's own published reference numbers (pass@1 ~99.9%,
13.1% vs. the documented "12.7% of gold patterns are ReDoS-vulnerable" —
close enough to be the 0.3.0→0.4.0 rescoring, not a bug) and the good/bad/
vulnerable control triad from §1.4 all still behave exactly as designed:
good passes everything, bad regular pattern fails everything including
`dfa-eq (decided)` (rather than landing in `n/a`, which is exactly the
failure mode §1.4 flagged and designed around), vulnerable-only fails
correctness but correctly flags 100% vulnerable.

### 0.3 What this changes in §1–3 below

- §1.3 point 3 and §3 blocker 1 (network egress) — **resolved**, superseded
  by §0.1.
- §1.3 point 2 (`seed` unverified) — still open; Phase 1 still needs to run
  the empirical probe.
- §2 Phase 0 runner design — add: pin by commit SHA (not version string)
  until `regexbench` 0.4.0 reaches PyPI; add a `crosscheck()` pass over
  committed controls as a fourth control check alongside good/bad/vuln.
- §2 Phase 1 step 4 (cost extrapolation) — now has a real number to check
  against: **$5 total** on this key. A dozen-plus models × k=5 × 762
  RegexEval tasks is very unlikely to fit in $5 even on cheap models; Phase
  1's extrapolation will very likely force either a smaller task
  sample, a smaller model roster, a smaller `k`, or a request for a
  higher-limit key before Phase 2 can run at the scale §2 originally
  sketched. Flagging this now rather than discovering it mid-Phase-1.
- §2 Phase 3 methodology write-up — the "Known limitations" table needs to
  drop lookaround from the `UNSUPPORTED` list and state the new decided
  fraction once Phase 1/2 numbers exist; backreferences stay as the one
  `UNDECIDABLE` construct.
- §3 — blockers 1 and 2 done; blocker 3 answered (capped at $5, contrary to
  the ≥$10-credits assumption the free-tier math in §1.3 point 1 depended
  on — that free-tier rate-limit correction is now moot for this key
  specifically, since $5 in credits already clears the unfunded tier
  either way).

**Rough affordability check** (pricing pulled from `/api/v1/models`, no
completions run yet — Phase 1 itself hasn't started): cheap models
(`meta-llama/llama-3.1-8b-instruct`, `qwen/qwen-2.5-7b-instruct`,
`gpt-4o-mini`) run $0.05–0.60 per million tokens, so a single-model,
ten-task Phase 1 dry run is a fraction of a cent regardless of which model
it uses — no reason to wait on a budget decision to run Phase 1 itself.
The real pressure point is Phase 2: even a mid-priced model at, say, $2/M
completion tokens, 762 tasks × k=5 samples × ~150 completion tokens/sample
≈ 570k tokens ≈ **$1.14 for one model** — meaning the $5 cap supports at
most 3–4 mid-priced models at the original full-corpus, k=5 scale, not
12–15. Phase 2 will need to trade off corpus size, `k`, or model count
once real Phase 1 numbers replace this estimate.

---

## 1. Validation report

### 1.1 Verified

| Handoff claim | Result |
| --- | --- |
| `regexbench` on PyPI, Apache-2.0, source at `github.com/foothills-labs/regexbench` | ✅ Installs; `License-Expression: Apache-2.0`; homepage matches |
| API: `from regexbench import run`; `datasets.load_regexeval / load_deep_regex / load_tasks` | ✅ All import on 0.3.0; `run(tasks, predictions, *, name, timeout, workers, progress)` |
| CLI: `regexbench run` with `--use-reference --workers --limit --k --json` + predictions file | ✅ All flags present. Predictions are a **JSON mapping** task-name → pattern (or list of patterns), or an aligned JSON array — not JSONL |
| Metrics: `pass@k`, `dfa-eq@k`, `exact@k`, `vulnerable@k`, `usable@k`, `dfa-eq@k (decided)`; unbiased Chen et al. pass@k | ✅ All appear in real output; README states the unbiased estimator |
| `usable` = correct AND not ReDoS-vulnerable; `Report.usable` | ✅ Confirmed in README and API |
| Backreferences → `UNDECIDABLE`, lookaround → `UNSUPPORTED`; report both dfa-eq forms | ✅ Confirmed; loaders never filter, undecidable count is printed with every table |
| `\d` is Unicode-aware (not `[0-9]`) | ✅ Confirmed — README shows `equivalent(r"\d", "[0-9]")` → `DIFFERENT`, witness `'٣'` |
| ReDoS `SAFE` is screening, not proof | ✅ Stated verbatim in README |
| OpenRouter default = load-balancing weighted by inverse square of price; `provider` fields `order`, `allow_fallbacks`, `quantizations`, `only`, `require_parameters`, `sort`, `ignore`, `data_collection`, `max_price` | ✅ Cross-checked against community references (openrouter.ai itself is egress-blocked here — see §1.3) |
| Resolved provider is recoverable per response | ✅ Top-level `provider` field in the response, plus `GET /api/v1/generation?id=...` for usage audit |
| LessWrong post on pinning | ✅ Exists at the cited URL. Actual title ends "…Might Invalidate Your **Research**", not "Evals". Content matches: inverse-square-price routing, silent quantization variance, params silently dropped unless `require_parameters` |
| 429 has no queue/auto-retry; caller must back off | ✅ Consistent with current community documentation |
| Datasets reachable | ✅ `RegexEval.json` downloads (1.0 MB, 762 tasks); `deep-regex` clones with KB13, NL-RX-Synth, NL-RX-Turk present |
| Pipeline end-to-end | ✅ Smoke-tested — see §1.4 |

### 1.2 Changed since the handoff was written

1. **`regexbench` is now 0.3.0** (released 2026-08-03, the day after the
   handoff; handoff says 0.2.0). Same API, but 0.3.0 **changes scoring
   behaviour**: `\xHH`/`\uHHHH`/`\N{NAME}`/octal escapes now parse correctly
   (previously literal text), anchors away from pattern edges are resolved
   instead of dropped, 114 false-equivalence verdicts around assertions were
   fixed, `{,n}` now reads as `{0,n}`, and 26 patterns moved from
   `EXPONENTIAL` to `SAFE` in the ReDoS screen. Any number we publish must
   cite **regexbench 0.3.0 exactly**; numbers produced under 0.2.0 are not
   comparable.
2. **The Python ≤3.13 limitation is stale.** The 3.14 `\B` change was
   addressed in 0.2.1, and 0.3.0's classifiers include 3.14. Our runner is
   on Python 3.11.15, so this was never a blocker — but METHODOLOGY.md must
   not repeat the handoff's claim. We still pin and record the exact Python
   version, because `re` behaviour is part of the measurement.

### 1.3 Wrong or unverifiable

1. **Free-tier rate limit is wrong.** Handoff says 20 req/min, **200
   req/day**. Current documentation: 20 req/min and **50 req/day** unfunded,
   or **1,000 req/day** once the account has ever purchased $10+ in credits.
   Doesn't change the design (the sweep is paid), but don't republish the
   number.
2. **`seed` remains unverified**, as the handoff flagged. Community evidence:
   supported by most endpoints but not trustworthy for bitwise determinism
   across providers or time. Treat runs as non-deterministic; Phase 1
   includes an empirical probe (same request twice, same seed, diff).
3. **openrouter.ai is unreachable from this environment** — the network
   egress policy denies it (CONNECT 403 at the gateway). This is the one
   hard blocker; see §3. `lesswrong.com` is also blocked (worked around via
   search; nothing operational needs it).
4. **Naming**: the repo existed as `regexleaderboard` — neither of the
   handoff's two candidates, and singular. The handoff's rule ("a
   leaderboard's URL is its identity — don't rename it later") stopped
   applying when the project stopped being a leaderboard: it was renamed
   **`regexeval-2026`** on 2026-08-20, the name saying what it is — one
   dated evaluation study — and GitHub redirects the old URL.

### 1.4 Smoke test performed (2026-08-07, Python 3.11.15, regexbench 0.3.0)

- `regexbench run regexeval RegexEval.json --use-reference --limit 25` →
  100% on every metric, 0% vulnerable. Corpus, semantics and dialect load
  correctly.
- Controls through the Python API on 5 tasks: known-good (the reference
  itself) → 100% across the board; known-bad → 0% `pass@1`, 0% `usable@1`.
- **Control-design lesson from the smoke test**: a known-bad built from
  lookahead (`(?!x)x`) lands in `UNDECIDABLE`, so `dfa-eq (decided)` reports
  `n/a` rather than 0%. The committed controls must use a *regular* wrong
  pattern (e.g. `z{5}`) so every metric, including the decided variant, is
  exercised — plus a separate deliberately-vulnerable control (e.g.
  `(a+)+b`) so a silently-broken ReDoS screen is also caught.

---

## 2. Implementation plan

### Phase 0 — scaffolding (no API key needed; can start immediately)

Repo layout as in the handoff:

```
runner/           OpenRouter client: pinning, retry/backoff, cost logging, parsing
tasks/            loader config + the small private task set
predictions/      raw model output, committed — the evidence
results/          scores and tables, dated
METHODOLOGY.md    updated for 0.3.0 realities (not the handoff's stale limits)
README.md         the leaderboard
PLAN.md           this file
docs/HANDOFF.md   the founding handoff, verbatim, for provenance
```

Runner design:

- **Config-driven model list** (`models.yaml`): one entry per model with
  slug, `provider.order`, `allow_fallbacks: false`,
  `quantizations`/`only` pin, `require_parameters: true`, `k`, temperature,
  max_tokens. The pin is part of the recorded config.
- **Every response logged raw** to `predictions/<model>/raw.jsonl`: request
  config, resolved `provider` from the response, usage/cost block,
  generation id, latency, full completion text, timestamp. A row without a
  resolved provider is treated as a failed request, never scored.
- **Response validation before scoring**: extract the pattern by a fixed,
  documented rule (last code-fenced block, else whole trimmed response);
  classify each response as `ok` / `parse_failure` / `refusal` /
  `http_error`. Parse failures are scored as wrong answers *and* reported
  as a separate rate (methodology rule 6) — a 429 body must never reach the
  scorer (failure mode 1).
- **Backoff and resume**: exponential backoff with jitter on 429/5xx;
  collection is idempotent per (model, task, sample-index) so an
  interrupted sweep resumes without re-buying completed samples.
- **Controls injected into every sweep**: known-good (reference), known-bad
  regular pattern, known-vulnerable pattern (per §1.4). A sweep whose
  controls don't come back 100% / 0% / vulnerable respectively is discarded.
- **Scoring wrapper**: converts raw.jsonl → the JSON mapping `regexbench
  run --predictions` expects (task name → list of k patterns), runs it,
  writes `results/<date>/<model>.json` (via `--json`) with the regexbench
  version, Python version, dataset SHA, and cost totals attached.

Task sets (open question 1 — recommendation):

- **Primary: Re(gEx|DoS)Eval** (762 tasks, real prompts, has positive/negative
  tests, search semantics) — comparable to the closest prior work and the
  only corpus where `pass@k`/`usable@k` are meaningful (KB13/NL-RX ship no
  examples, so only `dfa-eq` applies there).
- **Secondary: KB13** (824 tasks, BRICS dialect, dfa-eq only) for continuity
  with the older literature.
- **Contamination probe: ~30 hand-written private tasks** in
  `tasks/private/`, same schema as `load_tasks`, written fresh, never
  published before the run. The public-vs-private gap is a finding.
- Skip NL-RX-Synth/Turk for v1 (10k noisy synthetic tasks each; cost with
  little signal beyond KB13).

### Phase 1 — one model, ten tasks (blocked on §3)

1. Ten RegexEval tasks + the three controls through the full pipeline on
   one mid-priced model.
2. Verify in the logs: resolved provider matches the pin; quantization as
   requested; cost present per response; `allow_fallbacks: false` actually
   errors when the pinned provider is down (force it once with a fake
   provider slug).
3. **Seed probe**: identical request twice with `seed` set → diff. Answers
   open question 4 empirically; record the result in METHODOLOGY.md.
4. Extrapolate cost: (per-task tokens × k × tasks × models) from measured
   usage, before approving the sweep (handoff §8).

### Phase 2 — the sweep (needs budget sign-off from Phase 1 numbers)

- **k = 5, temperature 0.7, max_tokens 512** as the starting proposal:
  k=5 is the smallest k where pass@5 vs pass@1 is informative, and cost
  scales linearly in k (open question 2 — final call after Phase 1 pricing).
- **12–15 models, frontier + open-weights**, exact list drawn up once
  OpenRouter is reachable and current availability/pricing is visible
  (open question 3). Open-weights models matter most (fine-tune baseline);
  include at least one small/cheap model as a floor.
- Every model version-pinned by full slug; run dated; one raw.jsonl and one
  results JSON per model, all committed.

### Phase 3 — publish

- README table sorted by **`usable@1`**, with `pass@1`, both `dfa-eq`
  forms + decided fraction, `vulnerable@1`, parse-failure rate, and
  **cost per task** as columns. Date on the table.
- METHODOLOGY.md: pinning config, extraction rule, controls, engine
  limitations as they actually are in 0.3.0 (Unicode `\d`; decidable-subset
  caveat; `SAFE` = screening; search-semantics choice for RegexEval), and
  the one-command re-run.
- Failures section: refusals, prose-instead-of-pattern, provider errors —
  published, not dropped.

---

## 3. Blockers — needed from a human before Phase 1

1. ~~Allow `openrouter.ai` in this environment's network egress policy.~~
   **Resolved 2026-08-11** — see §0.1.
2. ~~`OPENROUTER_API_KEY` as an environment variable.~~ **Resolved
   2026-08-11** — set as `OPENROUTER_KEY`, valid, see §0.1.
3. ~~Confirm the account has ≥$10 lifetime credits.~~ **Answered, not as
   assumed** — this key is capped at **$5 total**, not open-ended with a
   $10 floor. That is now the binding constraint on Phase 2's scale; see
   §0.3. Still open: an explicit sign-off on whether $5 is the real budget
   for this leaderboard or just what happens to be on the key today, before
   Phase 1 commits to a task/model sample sized against it.
4. Sign-off on the §2 recommendations for task sets, k, and model list —
   defaults above will be used unless overridden. Given the $5 cap, this
   now needs to happen *with* Phase 1's cost extrapolation in hand, not
   before it — the original roster (12–15 models × k=5 × 762 tasks) is
   almost certainly unaffordable on this key and will need to shrink.

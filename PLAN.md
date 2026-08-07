# regexleaderboard — handoff validation & implementation plan

Written 2026-08-07, against [docs/HANDOFF.md](docs/HANDOFF.md) (dated
2026-08-02). Every claim in the handoff was checked from this environment
before this plan was written. Section 1 is what checked out, what changed,
and what is wrong; section 2 is the plan; section 3 is what is needed from
a human before Phase 1 can run.

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
4. **Naming**: the repo exists as `regexleaderboard` — neither of the
   handoff's two candidates, and singular. By the handoff's own rule
   ("a leaderboard's URL is its identity — don't rename it later") the name
   is now fixed; noting the deviation for the record, not proposing a rename.

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

1. **Allow `openrouter.ai` in this environment's network egress policy**
   (Claude Code on the web → environment settings → network policy). All
   HTTPS to it currently gets CONNECT 403 at the gateway. Nothing else on
   the critical path is blocked: PyPI, raw.githubusercontent.com, and
   git-clone of dataset repos all work.
2. **`OPENROUTER_API_KEY`** as an environment variable (already promised).
3. **Confirm the account has ≥$10 lifetime credits** (lifts platform limits)
   and give a rough budget ceiling for the sweep so Phase 1's extrapolation
   has something to be judged against.
4. Sign-off on the §2 recommendations for task sets, k, and model list —
   defaults above will be used unless overridden.

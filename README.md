# regexleaderboard

Natural-language → regex generation, scored on three axes that most regex
evals don't report together: **does it pass the tests**, **is it the same
language as the reference**, and **can it hang your server**.

Scoring is done by [`regexbench`](https://github.com/foothills-labs/regexbench),
an Apache-2.0 package this repo depends on and does not vendor. Predictions
are collected through OpenRouter with the provider and quantization pinned,
and every raw response is committed — the scores in this table are
recomputable from the evidence in `predictions/`.

> ### ⚠️ This is a PREVIEW, not the leaderboard
>
> The table below is a **10-task, k=1, 4-model pilot** run on 2026-08-11 to
> validate the pipeline end to end and to price the real sweep. **Ten tasks
> is far too few to rank models** — the confidence interval on a 10-task
> `pass@1` is roughly ±30 points. Read this as *proof the machine works and
> a preview of the artifact's shape*, not as a finding about these models.
> The full run (762 tasks, k=5) is costed in `PLAN.md` and not yet approved.

## Preview results — Re(gEx|DoS)Eval, 10 tasks, k=1, 2026-08-11

Sorted by `usable@1`, the headline metric: **correct *and* not
ReDoS-vulnerable**.

| Model | Provider (pinned) | usable@1 | pass@1 | dfa-eq@1 | dfa-eq@1 (dec.) | vulnerable@1 | resp. failures | $/task |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `openai/gpt-4o-mini` | OpenAI | **10.0%** | 40.0% | 10.0% | 12.5% | 20.0% | 0/10 | $0.000038 |
| `qwen/qwen-2.5-7b-instruct` | Together | 0.0% | 10.0% | 0.0% | 0.0% | 10.0% | 0/10 | $0.000047 |
| `meta-llama/llama-3.1-8b-instruct` | DeepInfra (fp8) | 0.0% | 20.0%* | 0.0% | 0.0% | 0.0% | 0/10 | $0.000003 |
| `mistralai/mistral-small-3.2-24b` | DeepInfra (fp8) | — | — | — | — | — | **10/10** | — |

`*` normalized score — see "The wrapper problem" below. Strict `pass@1` is 0.0%.

Scored with `regexbench` 0.4.0 (commit `05d7547b`), Python 3.11.15,
temperature 0.0, max_tokens 200, `k=1`. Total preview spend: **$0.000875**.

### What the preview already shows

**1. `usable@1` is not `pass@1`, and the gap is the point.** gpt-4o-mini
passes 40% of tasks but only 10% are *usable* — 20% of its patterns are
ReDoS-vulnerable, and others are proven-different from the reference
despite passing the given examples. A leaderboard reporting only
correctness would rank this model four times better than it deserves for
production use. This is the entire reason the repo exists, and it showed
up in ten tasks.

**2. A pinned provider that fails is visible, not silently substituted.**
`mistral-small-3.2` returned **0 usable responses out of 10**: DeepInfra
was rate-limited upstream (`engine_overloaded`), and because the request
set `allow_fallbacks: false`, OpenRouter refused to quietly reroute to
another provider at another quantization. That is the designed behaviour —
a visible failure beats an invisible substitution — and it is reported as
a response-failure rate rather than dropped from the table.

**3. The wrapper problem — a harness artifact that looks like model
failure.** Llama-3.1-8b returned five of ten answers wrapped in Python
raw-string syntax (`r'\d+$'` rather than `\d+$`). Scored literally, those
patterns match nothing and the model reads as 0% — scored after stripping
the wrapper, two become *fully correct* and `pass@1` goes 0% → 20%. That is
a 20-point swing produced entirely by an extraction decision in *our*
harness. Both numbers are reported, with the count of normalized responses,
and every strip is recorded in `results/` so the normalized score is
auditable against the raw response. **Small models are the ones this
penalizes**, so a leaderboard that quietly picked one rule would be
systematically unfair in a direction nobody could see.

**4. `dfa-eq` is brutally low, and `exact@1` is 0% for everyone.** No model
produced a pattern string-identical to the reference, and semantic
equivalence is in the 0–12.5% range even where `pass@1` is 40%. Passing the
examples is much easier than reproducing the reference language.

## Controls

Every model's run carries three synthetic controls through the identical
scoring path, because a scorer silently returning zeros looks exactly like
a model that failed:

| Control | Pattern | Expected | Observed |
| --- | --- | --- | --- |
| known-good | the task's own reference | passes, usable | ✅ 100% pass, usable |
| known-bad | `z{5}` | fails everything | ✅ 0% pass, 0% usable |
| known-vulnerable | `(a+)+b` | flagged vulnerable | ✅ 100% vulnerable |

All four models' control blocks came back as expected
(`controls_all_as_expected: true` in every `results/preview/*.json`),
including `mistral-small`, whose controls pass while its real requests all
failed — which is exactly how the controls prove the zero is a *collection*
failure and not a *scoring* failure.

## Reproduce

```bash
pip install "git+https://github.com/foothills-labs/regexbench.git@05d7547b1a71e6dd5cb00d71bf4dac7732be3ecd"
curl -O https://raw.githubusercontent.com/s2e-lab/RegexEval/master/DatasetCollection/RegexEval.json
export OPENROUTER_KEY=sk-or-...
python runner/run_preview.py     # collect (costs ~$0.001)
python runner/score_preview.py   # score; reads only committed responses
```

`score_preview.py` reads nothing but `predictions/` — you can re-score,
change the extraction rule, and see the effect without spending anything or
re-querying a model.

## Layout

```
runner/        OpenRouter client (pinning, backoff, cost logging) + scorer
predictions/   raw model responses, committed — the evidence
results/       scores as JSON, with provider/version/cost provenance
METHODOLOGY.md how it was run and every judgement call made
PLAN.md        validation of the founding handoff + the plan and its costs
docs/HANDOFF.md the founding brief, verbatim
```

## License

Code Apache-2.0. Re(gEx|DoS)Eval is redistributed by neither this repo nor
`regexbench`; download it from
[s2e-lab/RegexEval](https://github.com/s2e-lab/RegexEval).

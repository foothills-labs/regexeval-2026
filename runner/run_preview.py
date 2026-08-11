"""Phase 1 preview sweep: a handful of models x 10 tasks x k=1, real calls.

Not the full sweep -- this exists to produce a genuine, small, cheap slice
of what the real predictions/results/README artifacts will look like, so
it can be reviewed before committing budget to the full run.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from openrouter_client import call, extract_pattern  # noqa: E402

sys.path.insert(0, "/tmp/claude-0/-home-user-regexleaderboard/4f381924-048f-55c1-baa3-50487ddcdad5/scratchpad")
from regexbench.datasets import load_regexeval  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATASET = Path(
    "/tmp/claude-0/-home-user-regexleaderboard/4f381924-048f-55c1-baa3-50487ddcdad5"
    "/scratchpad/RegexEval.json"
)
PREVIEW_DIR = REPO / "predictions" / "preview"

TASK_INDICES = [0, 75, 150, 225, 300, 375, 450, 525, 600, 700]

MODELS = [
    {
        "slug": "openai/gpt-4o-mini",
        "label": "gpt-4o-mini",
        "provider": {"order": ["OpenAI"], "allow_fallbacks": False, "require_parameters": True},
    },
    {
        "slug": "meta-llama/llama-3.1-8b-instruct",
        "label": "llama-3.1-8b-instruct",
        "provider": {
            "order": ["DeepInfra"],
            "allow_fallbacks": False,
            "quantizations": ["fp8"],
            "require_parameters": True,
        },
    },
    {
        "slug": "qwen/qwen-2.5-7b-instruct",
        "label": "qwen-2.5-7b-instruct",
        "provider": {"order": ["Together"], "allow_fallbacks": False, "require_parameters": True},
    },
    {
        "slug": "mistralai/mistral-small-3.2-24b-instruct",
        "label": "mistral-small-3.2-24b",
        "provider": {
            "order": ["DeepInfra"],
            "allow_fallbacks": False,
            "quantizations": ["fp8"],
            "require_parameters": True,
        },
    },
]

# known-good / known-bad / known-vulnerable controls, injected into every model's run
CONTROLS = {
    "control/good": {
        "prompt": None,  # filled from reference at run time
        "task_name": "regexeval/1",  # reuse task 1's reference as the "good" answer
    },
}


def build_prompt(task) -> str:
    return (
        f"{task.prompt}\n\n"
        "Reply with only the regular expression pattern in a single fenced "
        "code block."
    )


def main():
    tasks = load_regexeval(str(DATASET))
    selected = [tasks[i] for i in TASK_INDICES]
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    for m in MODELS:
        out_path = PREVIEW_DIR / f"{m['label']}.jsonl"
        rows = []
        print(f"=== {m['label']} ===", flush=True)

        # 3 controls, reusing 3 of the selected tasks' references
        control_specs = [
            ("control/good", selected[0], selected[0].reference),
            ("control/bad", selected[1], "z{5}"),
            ("control/vulnerable", selected[2], "(a+)+b"),
        ]
        for cname, ctask, cpattern in control_specs:
            rows.append(
                {
                    "task_name": cname,
                    "base_task": ctask.name,
                    "prompt_sent": None,
                    "model_requested": m["slug"],
                    "provider_requested": m["provider"],
                    "status": "ok",
                    "provider_resolved": "n/a (synthetic control, no API call)",
                    "model_resolved": "n/a",
                    "content": cpattern,
                    "pattern": cpattern,
                    "usage": {},
                    "cost_usd": 0.0,
                    "latency_s": 0.0,
                    "generation_id": None,
                }
            )

        for task in selected:
            prompt = build_prompt(task)
            res = call(
                model=m["slug"],
                provider=m["provider"],
                prompt=prompt,
                temperature=0.0,
                max_tokens=200,
            )
            pattern = extract_pattern(res.content) if res.ok else None
            row = {
                "task_name": task.name,
                "prompt_sent": prompt,
                "model_requested": res.model_requested,
                "provider_requested": res.provider_requested,
                "status": res.status,
                "provider_resolved": res.provider_resolved,
                "model_resolved": res.model_resolved,
                "content": res.content,
                "pattern": pattern,
                "usage": res.usage,
                "cost_usd": res.cost_usd,
                "latency_s": res.latency_s,
                "generation_id": res.generation_id,
                "error": res.error,
            }
            rows.append(row)
            status_str = res.status if res.ok else f"FAIL:{res.status}"
            print(
                f"  {task.name:16s} {status_str:12s} "
                f"provider={res.provider_resolved} cost=${res.cost_usd} "
                f"pattern={pattern!r}",
                flush=True,
            )
            time.sleep(0.3)

        with out_path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"  -> wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()

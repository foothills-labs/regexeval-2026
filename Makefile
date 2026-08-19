# regexleaderboard -- everything runs from a clean clone with `make`.
.PHONY: setup score check collect clean help

PY ?= python3
RUN ?= preview
REGEXBENCH_PIN = regexbench==0.4.0

help:
	@echo "make setup   install the pinned scorer + download the corpus"
	@echo "make score   recompute scores from committed predictions (free, offline)"
	@echo "make check   same, and fail if they differ from committed results (CI)"
	@echo "make collect query models via OpenRouter -- needs OPENROUTER_KEY, costs money"

setup:
	$(PY) -m pip install --quiet --upgrade "$(REGEXBENCH_PIN)"
	@mkdir -p data
	@test -f data/RegexEval.json || curl -fsSL -o data/RegexEval.json \
	  https://raw.githubusercontent.com/s2e-lab/RegexEval/master/DatasetCollection/RegexEval.json
	@echo "setup ok: regexbench pinned, corpus at data/RegexEval.json"

score:
	$(PY) runner/score.py --run $(RUN)

check:
	$(PY) runner/score.py --run $(RUN) --check

collect:
	$(PY) runner/run_preview.py

clean:
	rm -rf data __pycache__ runner/__pycache__

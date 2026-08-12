#!/bin/bash
# Score every model in a run, one process per core.
#
# Scoring is GIL-bound, so N single-threaded processes beat one process
# with N worker threads, and running every model at once beats nothing --
# it just thrashes. This queues them at the core count.
#
#   runner/score_all.sh <run-name> [concurrency]
set -u
RUN="${1:-sweep}"
N="${2:-$(nproc)}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="${REGEXLB_SCORE_LOGS:-/tmp/scorelogs}"

cd "$REPO" || exit 1
mkdir -p "$LOGS"
export REGEXLB_WORKERS=1

models=$(ls predictions/"$RUN"/*.jsonl 2>/dev/null | xargs -n1 basename | sed 's/\.jsonl$//')
[ -z "$models" ] && { echo "no predictions in predictions/$RUN"; exit 1; }

echo "scoring $(echo "$models" | wc -l) model(s) from predictions/$RUN, $N at a time"
for m in $models; do
  while [ "$(jobs -rp | wc -l)" -ge "$N" ]; do sleep 5; done
  python3 runner/score.py --run "$RUN" --models "$m" > "$LOGS/$m.log" 2>&1 &
done
wait

python3 runner/score.py --run "$RUN" --merge

#!/usr/bin/env bash
# Run the load sweep for one scenario across the five load levels defined
# relative to the saturation elbow lambda* (0.5, 0.9, 1.0, 1.2, 1.5), with N
# repeated trials each. Requires k6 on PATH and the target stack already up.
#
# Usage:
#   scripts/run-sweep.sh S4 [LAMBDA_STAR] [N] [BASE_URL] [ALG]
# LAMBDA_STAR defaults to results/lambda_star.txt (written by analysis/elbow.py)
# or 200 if absent.
set -euo pipefail
cd "$(dirname "$0")/.."

SCEN="${1:?scenario, e.g. S4}"
LSTAR="${2:-$( [ -f results/lambda_star.txt ] && cat results/lambda_star.txt || echo 200 )}"
N="${3:-30}"
BASE="${4:-http://localhost:8081}"
ALG="${5:-RS256}"
DURATION="${DURATION:-60s}"

LEVELS=(0.5 0.9 1.0 1.2 1.5)
echo "== sweep $SCEN  lambda*=$LSTAR  N=$N  base=$BASE  alg=$ALG =="

# Hold a lock for the whole sweep so a second `make up-*`/`run-*` cannot tear the
# stack out from under a run in progress (that shows up as k6 reporting
# "dial tcp 127.0.0.1:8081: connect: connection refused" on every request).
LOCK="results/.sweep.lock"
mkdir -p results
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "ERROR: a sweep is already running (pid $(cat "$LOCK")). Refusing to start a second one." >&2
  exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# The stack must be reachable for a trial to mean anything. Without this the
# sweep would swallow the failure (k6 || true) and grind out every remaining
# trial against a dead target, producing hours of 100%-false-positive data.
require_up() {
  curl -fs -m 5 "$BASE/health" >/dev/null 2>&1 && return 0
  echo "" >&2
  echo "ERROR: $BASE is not reachable - the stack is down." >&2
  echo "       k6 reports this as: dial tcp 127.0.0.1:8081: connect: connection refused" >&2
  echo "       Bring it back with:  make up-$SCEN     then re-run:  make sweep-$SCEN N=$N" >&2
  exit 1
}
require_up

for lvl in "${LEVELS[@]}"; do
  RPS=$(python3 -c "print(int(round($LSTAR*$lvl)))")
  for trial in $(seq 1 "$N"); do
    OUT="results/summary_${SCEN}_rps${RPS}_${ALG}.json"
    DEST="results/summary_${SCEN}_rps${RPS}_${ALG}_t${trial}.json"
    if [ -f "$DEST" ]; then
      echo "-- $SCEN  level=$lvl  rps=$RPS  trial=$trial/$N  [skip: already have $DEST]"
      continue
    fi
    require_up
    echo "-- $SCEN  level=$lvl  rps=$RPS  trial=$trial/$N"
    rm -f "$OUT"
    # k6 exits non-zero on a crossed threshold too, which is a legitimate result
    # here, so failures are tolerated -- but a missing summary is not.
    BASE_URL="$BASE" LOAD_RPS="$RPS" DURATION="$DURATION" JWT_ALG="$ALG" \
      SCENARIO="$SCEN" k6 run --quiet loadgen/main.js || true
    if [ ! -f "$OUT" ]; then
      echo "ERROR: trial $trial produced no summary - aborting rather than logging bad data." >&2
      require_up   # prints the "stack is down" diagnosis when that is the cause
      exit 1
    fi
    mv "$OUT" "$DEST"   # preserve each trial (main.js overwrites the same name)
  done
done
echo "== sweep $SCEN complete; $(ls results/summary_${SCEN}_* 2>/dev/null | wc -l) files =="

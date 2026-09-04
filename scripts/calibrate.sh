#!/usr/bin/env bash
# Measure the saturation elbow lambda* from real S0 data. One clean pass:
#
#   1. clear results/ of summary_*.json and lambda_star.txt (the archive and
#      example-output are never touched),
#   2. bring up S0 on Docker Compose with the gateway rate limiter effectively
#      OFF, so the elbow measured is the *service's* elbow and not the limiter's,
#   3. run loadgen/main.js across a wide load grid, one trial each,
#   4. tear the stack down,
#   5. ingest + fit the elbow, writing the MEASURED lambda* to
#      results/lambda_star.txt,
#   6. print the verdict, naming the fix when the grid missed the elbow.
#
# THE LOAD GRID. It must straddle the elbow: several genuinely idle points below
# it (elbow.py averages the lowest third of the grid to get its p99 baseline) and
# several past it. With APP_BUSINESS_CPU_MS=12 the app burns 12 ms of CPU per
# request on a single-threaded Node event loop, so its ceiling is ~1000/12 = 83
# r/s and the knee sits below that. A grid starting at 100 r/s would begin *past*
# the elbow: every point saturated, the "baseline" itself seconds deep, and the
# reported lambda* would describe only how far into overload the grid ran.
#
# The grid is also dense below the knee on purpose. A coarse low end lets a
# partially-queueing point into the baseline band, which inflates the baseline,
# raises the 2x threshold with it, and pushes the reported elbow too high;
# scripts/calibrate_report.py fails the run when that happens. The default spans
# 10..200 r/s -- roughly 0.2x to 4x the elbow in the units that matter.
# Override for a different service speed:
#     make calibrate LOADS="100 200 400 800 1200 1800 2600"
set -euo pipefail
cd "$(dirname "$0")/.."

SCEN=S0
ALG="${ALG:-RS256}"
BASE="${BASE_URL:-http://localhost:8081}"
LOADS="${LOADS:-10 15 20 25 30 40 50 60 75 100 150 200}"
DURATION="${DURATION:-45s}"
WARMUP="${WARMUP:-10s}"
# Rate limiting effectively off: the calibration must see the app's own elbow.
CAL_RATE="${CAL_RATE:-1000000}"
CAL_BURST="${CAL_BURST:-20000}"
COMPOSE=(docker compose -f compose/docker-compose.yml --env-file "compose/scenarios/${SCEN}.env")
# Every profile in docker-compose.yml. A profile-gated service (envoy, opa) left
# running by an earlier scenario is NOT removed by `down --remove-orphans` while
# its profile is inactive, so it survives into this run. Naming them all on the
# way down guarantees calibration measures S0 alone.
ALL_PROFILES="S4,S5,S6,S6fo,S3off"

echo "== calibrate: scenario=$SCEN loads=[$LOADS] duration=$DURATION alg=$ALG =="
echo "== gateway rate limit forced OFF for calibration (NGINX_RATE=$CAL_RATE) =="

# ---- 1. clean results/, never the archive -------------------------------------
mkdir -p results
LOCK="results/.sweep.lock"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "ERROR: a sweep is already running (pid $(cat "$LOCK")). Refusing to calibrate over it." >&2
  exit 1
fi
echo $$ > "$LOCK"

# Only the top level: results/synthetic-archive/ and results/example-output/ are
# subdirectories, and -maxdepth 1 cannot reach into them.
n_before=$(find results -maxdepth 1 -name 'summary_*.json' | wc -l | tr -d ' ')
find results -maxdepth 1 -name 'summary_*.json' -delete
rm -f results/lambda_star.txt results/lambda_star.measured.txt results/tidy_runs.csv results/tidy_cells.csv results/elbow_table.csv
echo "-- cleaned $n_before summary_*.json + lambda_star.txt from results/ "\
"(kept $(find results/synthetic-archive -name '*.json' 2>/dev/null | wc -l | tr -d ' ') archived synthetic files)"

# ---- 2. bring the stack up ----------------------------------------------------
teardown() {
  echo "-- tearing down"
  NGINX_RATE="$CAL_RATE" NGINX_BURST="$CAL_BURST" COMPOSE_PROFILES="$ALL_PROFILES" \
    "${COMPOSE[@]}" down --remove-orphans --timeout 5 >/dev/null 2>&1 || true
  rm -f "$LOCK"
}
trap teardown EXIT

NGINX_RATE="$CAL_RATE" NGINX_BURST="$CAL_BURST" COMPOSE_PROFILES="$ALL_PROFILES" \
  "${COMPOSE[@]}" down --remove-orphans --timeout 5 >/dev/null 2>&1 || true
# Shell env beats --env-file in Compose, so this overrides S0.env's NGINX_RATE.
NGINX_RATE="$CAL_RATE" NGINX_BURST="$CAL_BURST" \
  "${COMPOSE[@]}" up -d --build --remove-orphans
scripts/wait-healthy.sh

# Confirm what actually landed in the containers rather than trusting the env-file.
CPU_MS=$(docker exec zta-fintech-app-1 printenv BUSINESS_CPU_MS 2>/dev/null || echo '?')
echo "-- app BUSINESS_CPU_MS=$CPU_MS ; gateway limit=$CAL_RATE r/s (off)"

# Let a saturated run drain before the next one starts, so its backlog is not
# charged to the following load level.
drain() {
  for _ in $(seq 1 30); do
    t=$(curl -s -o /dev/null -m 5 -w '%{time_total}' "$BASE/health" 2>/dev/null || echo 9)
    awk "BEGIN{exit !($t < 0.25)}" && return 0
    sleep 1
  done
}

# ---- 3. sweep the grid --------------------------------------------------------
for RPS in $LOADS; do
  OUT="results/summary_${SCEN}_rps${RPS}_${ALG}.json"
  DEST="results/summary_${SCEN}_rps${RPS}_${ALG}_t1.json"
  drain
  echo "-- $SCEN rps=$RPS ($DURATION)"
  rm -f "$OUT"
  # k6 exits non-zero on a crossed threshold, which is a legitimate result at
  # saturating load -- but a missing summary is not.
  BASE_URL="$BASE" LOAD_RPS="$RPS" DURATION="$DURATION" WARMUP="$WARMUP" \
    JWT_ALG="$ALG" SCENARIO="$SCEN" k6 run --quiet loadgen/main.js >/dev/null 2>&1 || true
  if [ ! -f "$OUT" ]; then
    echo "ERROR: rps=$RPS produced no summary — aborting rather than logging bad data." >&2
    curl -fs -m 5 "$BASE/health" >/dev/null 2>&1 || echo "       cause: $BASE is not reachable." >&2
    exit 1
  fi
  mv "$OUT" "$DEST"
  python3 - "$DEST" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
f = lambda v: "n/a" if v is None else f"{v:9.2f}"
print(f"   reqs={d['http_reqs']:>6}  p50={f(d['p50_ms'])}  p95={f(d['p95_ms'])}"
      f"  p99={f(d['p99_ms'])}  dropped={d.get('dropped_iterations', 0)}")
PY
done

# ---- 4. tear down before analysing (frees the CPU the analysis needs) ---------
teardown
trap - EXIT

# ---- 5. ingest + fit ----------------------------------------------------------
echo
echo "== ingest + elbow fit =="
python3 analysis/ingest.py
python3 analysis/elbow.py
# Re-ingest: the first pass normalised load_norm against the OLD lambda* (or the
# nominal fallback, since the clean step deleted the file). elbow.py has just
# written the measured one, so redo the axis against it.
python3 analysis/ingest.py >/dev/null
# Keep an immutable record. `make analyse`/`make check` re-run elbow.py, which
# rewrites lambda_star.txt from the full sweep (S6) -- this file preserves what
# calibration actually measured, so drift is visible instead of silent.
cp results/lambda_star.txt results/lambda_star.measured.txt 2>/dev/null || true

# ---- 6. verdict ---------------------------------------------------------------
python3 scripts/calibrate_report.py

# ---- 7. archive the calibration runs (only reached when the verdict PASSED) ---
# Calibration is a DIFFERENT experiment from the sweep: the rate limiter was
# forced off and the load grid runs far outside the sweep's 0.5-1.5 x lambda*
# range. Left in results/ these S0 rows would pool overloaded 4x-lambda* points
# into the S0 scenario the paper reports, and run-sweep.sh would skip the sweep's
# own trial 1 wherever a load level happened to coincide. results/calibration/ is
# a subdirectory, so ingest.py (non-recursive glob, plus an explicit quarantine
# entry) never sees it again.
mkdir -p results/calibration
n_cal=$(find results -maxdepth 1 -name 'summary_S0_*.json' | wc -l | tr -d ' ')
find results -maxdepth 1 -name 'summary_S0_*.json' -exec mv {} results/calibration/ \;
echo
echo "-- archived $n_cal calibration runs to results/calibration/ (never ingested)"
echo "   results/ is now empty of summaries and ready for the real sweep."

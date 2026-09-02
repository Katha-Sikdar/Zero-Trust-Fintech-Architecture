#!/usr/bin/env bash
# Bring up one scenario's stack (compose), wait for health, run the sweep, tear
# down. This is the single command per scenario.
#   scripts/run-scenario.sh S5 [N]
set -euo pipefail
cd "$(dirname "$0")/.."
SCEN="${1:?scenario S0..S6}"; N="${2:-30}"
echo "== $SCEN: up =="
docker compose -f compose/docker-compose.yml --profile "$SCEN" up -d --build
scripts/wait-healthy.sh
echo "== $SCEN: sweep =="
scripts/run-sweep.sh "$SCEN" "$( [ -f results/lambda_star.txt ] && cat results/lambda_star.txt || echo 200 )" "$N"
echo "== $SCEN: down =="
docker compose -f compose/docker-compose.yml --profile "$SCEN" down

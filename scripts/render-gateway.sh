#!/usr/bin/env bash
# Render nginx.conf with a scenario-specific rate limit.
#   ./render-gateway.sh 200   -> 200 r/s (default)
#   ./render-gateway.sh 260   -> S6 model-driven limit near lambda*
set -euo pipefail
RATE="${1:-200}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
sed "s/rate=200r\/s/rate=${RATE}r\/s/" "$DIR/gateway/nginx.conf" > "$DIR/gateway/nginx.rendered.conf"
echo "rendered gateway at ${RATE} r/s -> gateway/nginx.rendered.conf"

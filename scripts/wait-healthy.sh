#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
URL="${1:-http://localhost:8081/health}"
echo -n "waiting for $URL "
for i in $(seq 1 60); do
  if curl -fs "$URL" >/dev/null 2>&1; then echo " up"; exit 0; fi
  echo -n "."; sleep 1
done
echo " TIMEOUT"; exit 1

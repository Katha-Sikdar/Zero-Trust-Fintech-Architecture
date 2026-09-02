#!/usr/bin/env bash
# Apply a scenario overlay, wait for rollout, discover the ingress URL, and run
# the sweep against it. Tear down the scenario-specific policies afterwards.
#   scripts/k8s-run.sh S5 [N]
set -euo pipefail
cd "$(dirname "$0")/.."
SCEN="${1:?scenario S2..S6}"; N="${2:-30}"

# RequestAuthentication needs the JWKS inlined (see the script's header).
scripts/render-k8s-jwks.sh

# `kubectl apply -k` cannot relax kustomize's load restrictor, and the scenario
# overlays deliberately pull shared policy files from k8s/istio/ and policy/ -
# paths outside each overlay directory. Render first, then apply.
kubectl kustomize --load-restrictor LoadRestrictionsNone "k8s/scenarios/$SCEN" \
  | kubectl apply -f -
kubectl -n zta rollout status deploy/fintech-api --timeout=120s

# Ingress URL. On a cloud cluster the LoadBalancer has a real hostname/IP. On a
# local cluster it reports "localhost", which is NOT usable here: any other
# ingress controller (this cluster has a leftover ingress-nginx) also claims :80
# and answers first, and Docker Desktop does not expose NodePorts on localhost.
# So tunnel straight to the istio gateway.
#
# NOTE: the tunnel is a single kubectl proxy hop. It is fine for correctness runs
# but adds latency and can cap throughput, so it is a confound for the p95/p99
# numbers. For measurement runs, free port 80 for the mesh instead:
#   kubectl -n ingress-nginx scale deploy/ingress-nginx-controller --replicas=0
# and then set INGRESS_URL=http://localhost to bypass the tunnel.
HOST=$(kubectl -n istio-system get svc istio-ingressgateway \
        -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
[ -z "$HOST" ] && HOST=$(kubectl -n istio-system get svc istio-ingressgateway \
        -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)

if [ -n "${INGRESS_URL:-}" ]; then
  BASE="$INGRESS_URL"
elif [ -z "$HOST" ] || [ "$HOST" = localhost ] || [ "$HOST" = 127.0.0.1 ]; then
  PORT="${INGRESS_PORT:-18080}"
  kubectl -n istio-system port-forward svc/istio-ingressgateway "$PORT:80" >/dev/null 2>&1 &
  PF_PID=$!
  trap 'kill "$PF_PID" 2>/dev/null || true' EXIT
  BASE="http://localhost:$PORT"
  for _ in $(seq 1 30); do
    curl -fsS -m 2 -o /dev/null "$BASE/health" 2>/dev/null && break; sleep 1
  done
else
  BASE="http://$HOST"
fi
echo "ingress = $BASE"

# Confirm it is really the mesh answering before spending hours against it.
if ! curl -fsS -m 10 -o /dev/null "$BASE/health"; then
  echo "ERROR: $BASE/health did not answer 2xx - is the ingress reachable and the app up?" >&2
  curl -sS -o /dev/null -w "  got HTTP %{http_code} from %{url_effective}\n" -m 10 "$BASE/health" >&2 || true
  exit 1
fi

scripts/run-sweep.sh "$SCEN" "$( [ -f results/lambda_star.txt ] && cat results/lambda_star.txt || echo 200 )" "$N" "$BASE"

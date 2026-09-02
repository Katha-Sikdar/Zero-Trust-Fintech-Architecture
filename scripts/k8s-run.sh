#!/usr/bin/env bash
# Apply a scenario overlay, wait for rollout, discover the ingress URL, and run
# the sweep against it. Tear down the scenario-specific policies afterwards.
#   scripts/k8s-run.sh S5 [N]
set -euo pipefail
cd "$(dirname "$0")/.."
SCEN="${1:?scenario S2..S6}"; N="${2:-30}"

kubectl apply -k "k8s/scenarios/$SCEN"
kubectl -n zta rollout status deploy/fintech-api --timeout=120s

# ingress URL (works for EKS LoadBalancer or `istioctl` port-forward)
HOST=$(kubectl -n istio-system get svc istio-ingressgateway \
        -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
[ -z "$HOST" ] && HOST=$(kubectl -n istio-system get svc istio-ingressgateway \
        -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
BASE="http://${HOST:-localhost}"
echo "ingress = $BASE"

scripts/run-sweep.sh "$SCEN" "$( [ -f results/lambda_star.txt ] && cat results/lambda_star.txt || echo 200 )" "$N" "$BASE"

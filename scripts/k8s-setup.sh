#!/usr/bin/env bash
# One-time setup for the Istio (variable/cloud) testbed. Assumes kubectl points
# at your cluster (EKS, kind, or minikube) and istioctl is installed.
set -euo pipefail
cd "$(dirname "$0")/.."

# istioctl is not vendored. Prefer one on PATH; otherwise use the pinned copy in
# tools/, fetching it if needed so this script is self-sufficient.
ISTIO_VERSION="${ISTIO_VERSION:-1.28.0}"
ISTIOCTL="$(command -v istioctl 2>/dev/null || true)"
if [ -z "$ISTIOCTL" ]; then
  [ -x "tools/istio-${ISTIO_VERSION}/bin/istioctl" ] || scripts/get-istioctl.sh
  ISTIOCTL="$PWD/tools/istio-${ISTIO_VERSION}/bin/istioctl"
fi
echo "using istioctl: $ISTIOCTL ($("$ISTIOCTL" version --remote=false 2>/dev/null))"

# Fail here rather than half-way through the install if kubectl has no cluster.
kubectl cluster-info >/dev/null 2>&1 || {
  echo "kubectl cannot reach a cluster (context: $(kubectl config current-context 2>/dev/null || echo none))." >&2
  echo "Start Docker Desktop Kubernetes, kind, or minikube first." >&2; exit 1; }
echo "cluster: $(kubectl config current-context)"

echo "== 1. install Istio with the OPA ext_authz provider =="
"$ISTIOCTL" install -y -f k8s/istio/istio-extension-provider.yaml \
  --set profile=default || {
    echo "istioctl install failed — see the error above"; exit 1; }

echo "== 2. namespace + sidecar injection =="
kubectl apply -f k8s/base/namespace.yaml

echo "== 3. JWT keys secret (from app/keys) =="
kubectl -n zta create secret generic jwt-keys \
  --from-file=app/keys/rsa-public.pem \
  --from-file=app/keys/ec-public.pem \
  --dry-run=client -o yaml | kubectl apply -f -

echo "== 4. serve JWKS in-cluster so RequestAuthentication.jwksUri resolves =="
kubectl -n zta create configmap jwks --from-file=jwks.json=envoy/jwks.json \
  --dry-run=client -o yaml | kubectl apply -f -
# NOTE: for a self-contained setup, replace jwksUri in
# k8s/istio/request-authentication.yaml with an inline `jwks:` block:
#   kubectl -n zta get configmap jwks -o jsonpath='{.data.jwks\.json}'
echo
echo "Setup complete. Build/push the image to your registry, then:"
echo "  kubectl apply -k k8s/scenarios/S5"

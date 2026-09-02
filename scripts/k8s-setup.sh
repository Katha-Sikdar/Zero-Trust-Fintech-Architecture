#!/usr/bin/env bash
# One-time setup for the Istio (variable/cloud) testbed. Assumes kubectl points
# at your cluster (EKS, kind, or minikube) and istioctl is installed.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1. install Istio with the OPA ext_authz provider =="
istioctl install -y -f k8s/istio/istio-extension-provider.yaml \
  --set profile=default || {
    echo "istioctl install failed — install Istio >=1.20 and retry"; exit 1; }

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

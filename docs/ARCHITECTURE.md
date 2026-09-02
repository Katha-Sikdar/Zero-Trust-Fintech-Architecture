# Architecture

## Request path

```
 client (k6)                gateway            sidecar               app
 labelled  ──HTTP──▶  NGINX (PEP-1) ──▶  Envoy (PEP-2) ──▶  Node.js (PEP-3)
 benign+attack        rate limit         mTLS, JWT,           business logic
                      (API4)             ext_authz→OPA        (+ optional
                                         (API1/2/5/8, A10)     in-process authz)
                                              │
                                       OPA (authz.rego)
                                       BOLA/BFLA decision
```

The **enforcement point** for authentication and authorization moves between
PEP-2 (sidecar) and PEP-3 (app) depending on scenario. That movement is the
independent variable of the whole study.

## How one binary becomes seven scenarios

`app/src/config.js` reads two knobs:

- `JWT_MODE`  = `none | app | delegated` — who validates the token
- `AUTH_MODE` = `none | app | delegated` — who authorizes the action

`none` = not enforced (baseline), `app` = the Node.js process does it in-loop,
`delegated` = Envoy/Istio already did it and the app trusts the forwarded
`x-jwt-payload`. Compose sets these per scenario via `compose/scenarios/*.env`;
Kubernetes sets them via kustomize `configMapGenerator` literals in
`k8s/scenarios/*/kustomization.yaml`.

## Ground-truth scoring

`loadgen/lib/scoring.js` maps each response to a confusion-matrix cell using the
request's known label and the HTTP status. Per-risk counters are pre-declared in
`loadgen/lib/metrics.js`, so k6's `handleSummary` writes an exact matrix per
`(scenario, load)` with no heavy post-processing. The app also emits
`x-enforced-by` / `x-decision` headers and `app_fail_open_total` for corroboration.

## Two testbeds, one analysis

Both testbeds emit the identical `results/summary_*.json` schema, so
`analysis/` is agnostic to where the data came from — Compose, Istio, or the
synthetic generator. The elbow fit writes `results/lambda_star.txt`, which feeds
the graded load sweep back in the load generator.

## Fidelity notes

- **S2 (mesh-wide STRICT mTLS)** is fully realised only on the Istio testbed
  (`PeerAuthentication`). On Compose it is approximated (TLS at the gateway +
  a small added service cost) because real mTLS needs Envoy-to-Envoy. The
  security-efficacy results for S3–S6 are fully realised on both.
- **Adaptive rate limit (S6)** uses NGINX `limit_req` on Compose and an Istio
  `EnvoyFilter` local-rate-limit on Kubernetes. Both expose the same actuator the
  RQ3 model tunes.

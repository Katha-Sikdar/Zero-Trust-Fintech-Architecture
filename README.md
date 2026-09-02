# ZTA FinTech Testbed

A complete, runnable implementation of the MSc study
**"Adaptive Zero Trust for FinTech APIs: Measuring the Security–Performance
Frontier of Policy Enforcement Placement in Event-Driven Runtimes."**

It builds the artefact, generates OWASP-aligned adversarial load, measures both
latency **and** security efficacy on the same runs, and reduces the output to the
tables and figures in the proposal. You execute it and analyse the results.

---

## What's in the box

| Layer | Path | What it is |
|---|---|---|
| Target API | `app/` | Node.js FinTech service; enforcement is **config-driven** so one binary is all seven scenarios (S0–S6) |
| Enforcement | `envoy/`, `policy/`, `gateway/` | Envoy sidecar (JWT + ext_authz), OPA policy (BOLA/BFLA), NGINX gateway (rate limit) |
| Attack corpus | `loadgen/` | k6 scripts for **all five in-scope risks** + benign traffic, labelled for a per-risk confusion matrix |
| Testbed A | `compose/` | Docker Compose — the deterministic control (Apple M4) |
| Testbed B | `k8s/` | Kubernetes + Istio — the variable/cloud environment (AWS EKS) |
| Analysis | `analysis/` | Ingest → elbow fit (Kingman G/G/1 + P–K M/G/1) → stats (ANOVA / t-test / Wilson / Fisher) → tables + figures |
| Synthetic data | `analysis/synth/` | Generates realistic **stamped-synthetic** results so the analysis runs before any infra is up |

The seven core scenarios plus three experiment arms:

| ID | Configuration | Answers |
|---|---|---|
| S0 | Baseline (HTTPS only) | control |
| S1 | Edge TLS | RQ1 |
| S2 | Full mesh mTLS (STRICT) | RQ1, API8 |
| S3 | Application-layer JWT + in-process authz | RQ1, RQ4 |
| S4 | Sidecar JWT offloading (Envoy) | RQ1, RQ4 |
| S5 | Sidecar JWT + OPA authorization | RQ4 |
| S6 | S5 + model-driven adaptive rate limit | RQ3, RQ4, RQ5 |
| S6fo | S6 but Envoy **fail-open** | RQ5 (the A10 contrast) |
| S4es | S4 with **ES256** instead of RS256 | RQ2 |
| S3off | S3 with **worker_threads** offload | RQ1 |

---

## Quick start (three levels of commitment)

### 1. Analysis only — no Docker, ~30 seconds
Proves the whole measurement + analysis path works. Generates synthetic results
(clearly stamped) and produces every table and figure.

```bash
pip install -r analysis/requirements.txt
make demo
open results/figures/          # figA_elbow, figB_failopen, figC_frontier, figD_coverage_heatmap
cat  results/stats_report.md    # ANOVA, t-tests, Wilson CIs, Fisher, RQ5 table
```
`results/example-output/` already contains a committed sample of exactly this.

### 2. Real measurement on Docker Compose — the deterministic testbed
Needs Docker and [k6](https://k6.io/docs/get-started/installation/).

```bash
make tokens                 # mint keys + JWKS + the attack-token corpus (once)
make run-S3 N=30            # one scenario end-to-end (up → sweep → down)
make all-compose N=30       # every scenario, then analyse   (long run)
make analyse                # (re)build tables + figures from results/
```

Run **S0 first once** to let the elbow fit estimate λ\*, which then drives the
graded load sweep (0.5–1.5 × λ\*) for the rest.

### 3. Real measurement on Kubernetes + Istio — the variable testbed
Needs `kubectl` + `istioctl` pointed at a cluster (EKS, kind, or minikube) and
the image pushed to a registry your cluster can pull.

```bash
make k8s-setup              # install Istio (+OPA ext_authz provider), namespace, keys
make k8s-S5 N=30            # apply overlay S5, run the sweep against the ingress
make analyse
```

---

## The measurement, in one paragraph

Every k6 request is tagged with ground truth (`benign` or `attack:<risk>`) before
it is sent, and its response is scored into a per-risk confusion matrix:
`attack → 2xx` is a **bypass** (false negative), `attack → non-2xx` is a **block**
(true positive), `benign → non-2xx` is a **false positive**. The same run records
p50/p95/p99 latency. So one execution yields both axes — cost and benefit — under
identical load. Sweeping load around λ\* and comparing the fail-closed (S6) and
fail-open (S6fo) mesh is the RQ5 experiment: whether enforcement quietly stops
working past the saturation elbow (OWASP A10:2025).

See `docs/RUNBOOK.md` for the full step-by-step, `docs/ARCHITECTURE.md` for how
the pieces fit, and `docs/OWASP-MAPPING.md` for the risk-to-control mapping.

---

## Ethics & safety

All attack traffic runs against **your own** isolated deployment (local Compose or
a dedicated cluster). No real financial data, PII, or third-party endpoint is
involved. The corpus contains no working exploit against any external system —
only the malformed tokens and unauthorised requests needed to test the testbed's
own enforcement. This mirrors Section 9 of the proposal.

> **Synthetic vs measured.** `make demo` data is stamped `synthetic: true` and every
> figure carries a "SYNTHETIC DATA" mark. Once you run the real testbed, the same
> analysis reads your measured `results/summary_*.json` and the stamp disappears.

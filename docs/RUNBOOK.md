# Runbook

## 0. Prerequisites
- Analysis only: Python 3.10+ and `pip install -r analysis/requirements.txt`.
- Compose testbed: Docker + Docker Compose, `k6`, Node.js 20+ (to mint tokens).
- Istio testbed: `kubectl`, `istioctl` (≥1.20), a cluster, a container registry.

## 1. Prove the analysis path (no infra)
```bash
make demo
```
Inspect `results/stats_report.md`, `results/tables.md`, `results/figures/`.

## 2. First real run (Compose)
```bash
make tokens           # keys + JWKS + attack corpus
# calibrate the elbow with a quick baseline sweep:
make run-S0 N=5
python3 analysis/elbow.py          # writes results/lambda_star.txt
# now the graded sweep for the scenarios you care about:
make run-S3 N=30
make run-S4 N=30
make run-S5 N=30
make run-S6 N=30
make run-S6fo N=30    # the fail-open contrast for RQ5
make run-S4es N=30    # ES256 for RQ2
make analyse
```

## 3. Full Compose matrix (unattended)
```bash
make all-compose N=30      # S0..S6 + arms, then analyse. Hours, depending on N.
```

## 4. Istio / EKS
```bash
# build + push the image to your registry, edit the image ref in k8s/base/app.yaml
make k8s-setup
make k8s-S5 N=30
make analyse
```
Grafana panels to watch are listed in `k8s/monitoring/README.md`.

## 5. Interpreting the outputs
- `results/stats_report.md` — §2 has the RQ1/RQ2 contrasts; §4 the RQ4 Fisher
  test (does authorization offloading matter); §5 the RQ5 fail-open table.
- `results/tables.md` — coverage-vs-cost per scenario, and the confusion matrix.
- `results/figures/figC_frontier.png` — the security–performance frontier, the
  headline result.
- `results/elbow_table.csv` — per-scenario λ\* and fitted service rate.

## Troubleshooting
- **k6 "connection refused"** — the stack isn't up; run `make up-S5` and wait for
  `scripts/wait-healthy.sh` to report healthy.
- **All attacks show as bypassed in S4** — expected: S4 offloads JWT but not
  authorization. BOLA/BFLA/A10 are only covered from S5 on.
- **Elbow at the top of the sweep range** — raise the load ceiling: the scenario's
  capacity is above 1.5 × the λ\* you calibrated; re-run `elbow.py` on a wider S0.

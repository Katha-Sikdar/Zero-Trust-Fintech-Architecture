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

**Move any synthetic data out of `results/` first.** `ingest.py` reads every
`summary_*.json` in that directory, so a leftover synthetic corpus is silently
averaged into the measured one and stamps every table SYNTHETIC:
```bash
mkdir -p results/synthetic-archive && mv results/summary_*.json results/synthetic-archive/
rm -f results/lambda_star.txt      # a synthetic lambda* must not drive a measured sweep
```

```bash
make tokens           # keys + JWKS + attack corpus
# calibrate the elbow with a quick baseline sweep:
make run-S0 N=5
python3 analysis/elbow.py          # writes results/lambda_star.txt
# CHECK: elbow_table.csv must show status "ok" for S0. "no elbow in tested
# range" means the load ceiling is below saturation -- widen it (see
# Troubleshooting) before spending hours on the graded sweep.
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
- `results/stats_report.md` — §2 has the RQ1/RQ2 contrasts; §3 block rates with
  95% CIs computed over trials; §4 the RQ4 contrast (Mann-Whitney U on per-trial
  block rates: does authorization offloading matter); §5 the RQ5 fail-open table.
  Every p-value is Holm-Bonferroni corrected across the reported family.
- `results/tables.md` — coverage-vs-cost per scenario, and the confusion matrix.
- `results/figures/figC_frontier.png` — the security–performance frontier, the
  headline result.
- `results/elbow_table.csv` — per-scenario λ\* and fitted service rate.

## Troubleshooting
- **k6 "connection refused"** — the stack isn't up; run `make up-S5` and wait for
  `scripts/wait-healthy.sh` to report healthy.
- **All attacks show as bypassed in S4** — expected: S4 offloads JWT but not
  authorization. BOLA/BFLA/A10 are only covered from S5 on.
- **`elbow_table.csv` says "no elbow in tested range"** — the scenario's capacity
  is above 1.5 × the λ\* you calibrated, so the sweep never reached saturation.
  Raise the ceiling and re-run: `DURATION=30s scripts/run-sweep.sh S0 <bigger-lambda> 5`,
  then `python3 analysis/elbow.py`. The elbow is genuinely unestimable from the
  data until then — the column reports NaN rather than pinning it to the grid edge.
- **`elbow_table.csv` says "no p99 recorded"** — the k6 script must set
  `summaryTrendStats` including `'p(99)'` (it does since the fix in `loadgen/main.js`);
  summary files written before that carry `p99_ms: null` and are dropped from the fit.
- **Tables stamped SYNTHETIC when you expect measured** — a `summary_*.json` with
  `"synthetic": true` is still in `results/`. See step 2.

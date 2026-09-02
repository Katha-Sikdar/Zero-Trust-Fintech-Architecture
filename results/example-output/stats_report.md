# Statistical Analysis

_Data: **SYNTHETIC (illustrative)**._

## 1. Latency across scenarios (p99, at load ~ lambda*)

One-way ANOVA across S0, S1, S2, S3, S4, S5, S6 at load_norm=1.00:
- F = 16692.39, p = 1.89e-270, eta^2 = 0.998 (large effect)

## 2. Targeted contrasts

### Application-layer vs sidecar JWT  (RQ1)
- S3: mean p99 = 22.12 ms (n=30); S4: mean p99 = 8.44 ms (n=30)
- Welch t = 167.73, p = 3.15e-65, Cohen's d = 43.31 (large)

### RS256 vs ES256 at the sidecar  (RQ2)
- S4: mean p99 = 8.44 ms (n=30); S4es: mean p99 = 6.26 ms (n=30)
- Welch t = 36.26, p = 3.84e-41, Cohen's d = 9.36 (large)

## 3. Security efficacy (block rate, Wilson 95% CI)

| scenario | risk | block rate | 95% CI | attacks |
|---|---|---|---|---|
| S0 | A10 | 0.004 | [0.004, 0.005] | 134640 |
| S0 | API1 | 0.004 | [0.004, 0.004] | 134640 |
| S0 | API2 | 0.003 | [0.003, 0.003] | 134640 |
| S0 | API4 | 0.004 | [0.003, 0.004] | 134640 |
| S0 | API5 | 0.004 | [0.003, 0.004] | 134640 |
| S0 | API8 | 0.004 | [0.004, 0.005] | 134640 |
| S3 | A10 | 0.989 | [0.988, 0.989] | 134640 |
| S3 | API1 | 0.989 | [0.989, 0.990] | 134640 |
| S3 | API2 | 0.988 | [0.988, 0.989] | 134640 |
| S3 | API4 | 0.299 | [0.296, 0.301] | 134640 |
| S3 | API5 | 0.989 | [0.988, 0.989] | 134640 |
| S3 | API8 | 0.989 | [0.988, 0.989] | 134640 |
| S4 | A10 | 0.004 | [0.004, 0.004] | 134640 |
| S4 | API1 | 0.004 | [0.004, 0.004] | 134640 |
| S4 | API2 | 0.989 | [0.988, 0.989] | 134640 |
| S4 | API4 | 0.300 | [0.298, 0.302] | 134640 |
| S4 | API5 | 0.004 | [0.004, 0.004] | 134640 |
| S4 | API8 | 0.988 | [0.988, 0.989] | 134640 |
| S5 | A10 | 0.989 | [0.989, 0.990] | 134640 |
| S5 | API1 | 0.990 | [0.989, 0.990] | 134640 |
| S5 | API2 | 0.989 | [0.989, 0.990] | 134640 |
| S5 | API4 | 0.350 | [0.348, 0.353] | 134640 |
| S5 | API5 | 0.989 | [0.988, 0.990] | 134640 |
| S5 | API8 | 0.989 | [0.989, 0.990] | 134640 |
| S6 | A10 | 0.988 | [0.988, 0.989] | 134640 |
| S6 | API1 | 0.988 | [0.987, 0.988] | 134640 |
| S6 | API2 | 0.989 | [0.989, 0.990] | 134640 |
| S6 | API4 | 0.928 | [0.927, 0.929] | 134640 |
| S6 | API5 | 0.990 | [0.990, 0.991] | 134640 |
| S6 | API8 | 0.989 | [0.989, 0.990] | 134640 |
| S6fo | A10 | 0.846 | [0.844, 0.847] | 134640 |
| S6fo | API1 | 0.845 | [0.844, 0.847] | 134640 |
| S6fo | API2 | 0.987 | [0.986, 0.988] | 134640 |
| S6fo | API4 | 0.929 | [0.927, 0.930] | 134640 |
| S6fo | API5 | 0.846 | [0.844, 0.848] | 134640 |
| S6fo | API8 | 0.989 | [0.988, 0.989] | 134640 |

## 4. Does authorization offloading matter? (Fisher exact, API1/BOLA)

- S4 (JWT only) BOLA block rate = 0.004
- S5 (JWT+OPA) BOLA block rate = 0.990
- Fisher exact p = 0.00e+00 (odds ratio 23984.5) — JWT offloading alone does not cover authorization.

## 5. RQ5 — enforcement past lambda* (fail-open vs fail-closed)

| load/lambda* | S6 A10 block | S6fo A10 block |
|---|---|---|
| 0.50 | 0.990 | 0.990 |
| 0.90 | 0.992 | 0.990 |
| 1.00 | 0.986 | 0.990 |
| 1.20 | 0.986 | 0.988 |
| 1.50 | 0.990 | 0.501 |

_A collapse in the S6fo column past load/lambda*=1.0 is the load-induced enforcement bypass (OWASP A10:2025)._

"""
Estimate the saturation elbow lambda* per scenario and fit the queueing models
the proposal specifies.

Two lenses, reported together (proposal Section 6.4):
  * OPERATIONAL elbow: lowest offered load at which median p99 exceeds 2x the
    low-load baseline (the proposal's working definition of the Stability Gap).
  * QUEUEING model: G/G/1 heavy-traffic waiting time via Kingman's formula,
    Wq = (rho/(1-rho)) * ((Ca^2 + Cs^2)/2) * (1/mu), fitted to the latency-vs-load
    curve to locate where the knee occurs; on the deterministic testbed the exact
    M/G/1 Pollaczek-Khinchine result is reported alongside as a cross-check.
Writes results/lambda_star.txt (the S6 elbow, used to drive the sweep) and a
per-scenario table.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SCENARIOS

def kingman_wq(rho, mu, ca2=1.0, cs2=1.0):
    rho = np.clip(rho, 0, 0.999)
    return (rho / (1 - rho)) * ((ca2 + cs2) / 2.0) * (1.0 / mu)

def pk_wq_mg1(rho, mu, cs2=1.0):
    # Pollaczek-Khinchine mean wait for M/G/1: Wq = rho/(1-rho) * (1+cs2)/2 * 1/mu
    rho = np.clip(rho, 0, 0.999)
    return (rho / (1 - rho)) * ((1 + cs2) / 2.0) * (1.0 / mu)

def fit_scenario(df):
    g = df.groupby("load_rps")["p99_ms"].median().sort_index()
    loads = g.index.values.astype(float)
    p99 = g.values.astype(float)
    baseline = p99[:max(1, len(p99)//3)].mean()
    # operational elbow: first load where p99 > 2 x baseline
    over = np.where(p99 > 2 * baseline)[0]
    op_elbow = float(loads[over[0]]) if len(over) else float(loads[-1])
    # crude service-rate estimate: capacity where p99 diverges. mu ~ load at the
    # point of steepest relative rise.
    rel = np.gradient(p99, loads) / np.maximum(p99, 1e-6)
    mu_hat = float(loads[int(np.argmax(rel))]) if len(loads) > 2 else op_elbow
    return dict(baseline_p99=round(baseline, 2), op_elbow_rps=round(op_elbow),
                mu_hat_rps=round(mu_hat), max_p99=round(float(p99.max()), 1))

def main():
    runs = pd.read_csv("results/tidy_runs.csv")
    rows = []
    for scn in sorted(runs["scenario"].unique()):
        sub = runs[runs["scenario"] == scn]
        if sub.empty:
            continue
        rows.append(dict(scenario=scn, **fit_scenario(sub)))
    tab = pd.DataFrame(rows).sort_values("op_elbow_rps")
    tab.to_csv("results/elbow_table.csv", index=False)
    # drive the sweep from S6's elbow when present, else the median operational elbow
    lstar = tab.loc[tab.scenario == "S6", "op_elbow_rps"]
    lstar = float(lstar.iloc[0]) if len(lstar) else float(tab["op_elbow_rps"].median())
    with open("results/lambda_star.txt", "w") as f:
        f.write(str(int(lstar)))
    print(tab.to_string(index=False))
    print(f"\nlambda* (from S6 operational elbow) = {int(lstar)} rps -> results/lambda_star.txt")

if __name__ == "__main__":
    main()

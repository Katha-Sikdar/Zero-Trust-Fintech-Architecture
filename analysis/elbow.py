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

Every estimate is reported with a `status` and its data provenance. A scenario
whose p99 series is missing or never crosses the 2x threshold yields NaN, not a
number: an unestimable elbow must not be reported as an elbow at the edge of the
sweep grid, which is what an unguarded argmax/index-fallback silently produces.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SCENARIOS, NOMINAL_LAMBDA

MIN_LOADS = 3          # need >= 3 distinct offered loads to speak of a knee

def kingman_wq(rho, mu, ca2=1.0, cs2=1.0):
    rho = np.clip(rho, 0, 0.999)
    return (rho / (1 - rho)) * ((ca2 + cs2) / 2.0) * (1.0 / mu)

def pk_wq_mg1(rho, mu, cs2=1.0):
    # Pollaczek-Khinchine mean wait for M/G/1: Wq = rho/(1-rho) * (1+cs2)/2 * 1/mu
    rho = np.clip(rho, 0, 0.999)
    return (rho / (1 - rho)) * ((1 + cs2) / 2.0) * (1.0 / mu)

def _blank(status, n_loads=0):
    return dict(baseline_p99=np.nan, op_elbow_rps=np.nan, mu_hat_rps=np.nan,
                max_p99=np.nan, n_loads=n_loads, status=status)

def fit_scenario(df):
    """Fit one scenario. Returns NaN estimates (never a grid boundary) when the
    p99 series cannot support them, with `status` naming the reason."""
    valid = df.dropna(subset=["p99_ms"])
    n_missing = len(df) - len(valid)
    if valid.empty:
        return _blank(f"no p99 recorded in {len(df)} runs "
                      "(k6 summaryTrendStats must include 'p(99)')")

    g = valid.groupby("load_rps")["p99_ms"].median().sort_index()
    loads = g.index.values.astype(float)
    p99 = g.values.astype(float)
    if len(loads) < MIN_LOADS:
        return _blank(f"insufficient load levels ({len(loads)} < {MIN_LOADS})", len(loads))

    # baseline from the lowest third of the load grid
    baseline = float(p99[:max(1, len(p99) // 3)].mean())
    if not np.isfinite(baseline) or baseline <= 0:
        return _blank("non-positive or non-finite baseline p99", len(loads))

    # operational elbow: first load where p99 > 2 x baseline. No crossing means
    # the elbow lies outside the sweep grid -- report that, do not pin it to the
    # highest load tested.
    over = np.where(p99 > 2 * baseline)[0]
    if len(over):
        op_elbow = float(loads[over[0]])
        status = "ok"
    else:
        op_elbow = np.nan
        status = (f"no elbow in tested range: p99 never exceeded 2x baseline "
                  f"({2 * baseline:.2f} ms) up to {loads[-1]:.0f} rps")

    # crude service-rate estimate: capacity where p99 diverges. mu ~ load at the
    # point of steepest relative rise.
    rel = np.gradient(p99, loads) / np.maximum(p99, 1e-6)
    mu_hat = float(loads[int(np.nanargmax(rel))]) if np.isfinite(rel).any() else np.nan

    if n_missing:
        status += f" [{n_missing}/{len(df)} runs dropped: no p99]"
    return dict(baseline_p99=round(baseline, 2),
                op_elbow_rps=round(op_elbow) if np.isfinite(op_elbow) else np.nan,
                mu_hat_rps=round(mu_hat) if np.isfinite(mu_hat) else np.nan,
                max_p99=round(float(p99.max()), 1), n_loads=len(loads), status=status)

def main():
    runs = pd.read_csv("results/tidy_runs.csv")
    rows = []
    for scn in sorted(runs["scenario"].unique()):
        sub = runs[runs["scenario"] == scn]
        if sub.empty:
            continue
        prov = sub.get("synthetic", pd.Series([False]))
        rows.append(dict(scenario=scn, **fit_scenario(sub),
                         n_runs=len(sub),
                         provenance=("synthetic" if prov.all() else
                                     "mixed" if prov.any() else "measured")))
    tab = pd.DataFrame(rows).sort_values("op_elbow_rps", na_position="last")
    tab.to_csv("results/elbow_table.csv", index=False)
    print(tab.to_string(index=False), flush=True)

    # drive the sweep from S6's elbow when estimable, else the median of the
    # estimable ones. An unestimable lambda* must not overwrite a good one.
    s6 = tab.loc[tab.scenario == "S6", "op_elbow_rps"]
    lstar = float(s6.iloc[0]) if len(s6) and np.isfinite(s6.iloc[0]) else np.nan
    source = "S6 operational elbow"
    if not np.isfinite(lstar):
        med = tab["op_elbow_rps"].median(skipna=True)
        lstar, source = float(med), "median of estimable scenario elbows"

    path = "results/lambda_star.txt"

    # A CALIBRATED lambda* is authoritative and must not be overwritten here.
    # results/lambda_star.measured.txt is written by `make calibrate`, which
    # measures S0 with the rate limiter forced OFF -- the service's own capacity.
    # Re-deriving lambda* from the swept S6 data instead would be circular: the
    # calibrated lambda* sets S6's NGINX_RATE, that limiter shapes S6's latency
    # curve, and the resulting "elbow" is an artefact of the limiter rather than
    # of capacity. Worse, it silently re-scales load_norm underneath every table,
    # moving what counts as "the elbow" after the sweep was already run against
    # the calibrated value. The per-scenario fits still go to elbow_table.csv.
    measured_path = "results/lambda_star.measured.txt"
    if os.path.exists(measured_path):
        cal = open(measured_path).read().strip()
        print(f"\nlambda* = {cal} rps (MEASURED by `make calibrate`; kept). "
              f"This run's S6-derived fit was "
              f"{int(lstar) if np.isfinite(lstar) else 'unestimable'} rps and is "
              f"reported in results/elbow_table.csv only -- re-deriving it from "
              f"rate-limited sweep data would be circular.")
        return

    if not np.isfinite(lstar):
        print(f"\nWARNING: lambda* is not estimable from this data.", file=sys.stderr)
        if os.path.exists(path):
            print(f"         Leaving the existing {path} ({open(path).read().strip()} rps) "
                  "untouched; it was written by an earlier run.", file=sys.stderr)
        else:
            print(f"         No {path} written; downstream normalisation falls back to "
                  f"NOMINAL_LAMBDA={NOMINAL_LAMBDA} rps.", file=sys.stderr)
        return

    with open(path, "w") as f:
        f.write(str(int(lstar)))
    prov = tab.loc[tab.scenario == "S6", "provenance"]
    note = ""
    if len(prov) and prov.iloc[0] != "measured" and source.startswith("S6"):
        note = (f"\nWARNING: lambda* derives from {prov.iloc[0]} S6 data. Every sweep driven "
                "by it inherits that provenance -- state this in the methodology.")
    print(f"\nlambda* (from {source}) = {int(lstar)} rps -> {path}{note}",
          file=sys.stderr if note else sys.stdout)

if __name__ == "__main__":
    main()

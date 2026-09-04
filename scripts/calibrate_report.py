"""Print the calibration verdict: the MEASURED lambda*, or the reason the grid
failed to bracket the elbow and which knob to turn.

Two ways a calibration grid can miss, and they need opposite fixes:
  * p99 never rises  -> the service is faster than the whole grid. Raise
    APP_BUSINESS_CPU_MS (or extend the grid upward) and re-run.
  * p99 is already elevated at the LOWEST load -> the grid starts past the elbow,
    so the "baseline" is itself saturated and any crossing found is an artefact
    of overload depth, not an elbow. Lower APP_BUSINESS_CPU_MS or extend the grid
    downward and re-run.
  * the BASELINE BAND is contaminated -> elbow.py averages the lowest third of the
    grid to get its baseline p99. If any point in that band is already queueing,
    the baseline is inflated, the 2x threshold moves up with it, and the reported
    elbow lands at too high a load. The grid needs more resolution BELOW the knee,
    not a different CPU setting.
Only a run that clears all three gets to call its lambda* measured.
"""
import os, sys
import pandas as pd

BAR = "=" * 72
# A run whose p99 already exceeds this multiple of its own p50 at the lowest
# offered load is queueing, not idling -- the grid began past the knee.
SATURATED_RATIO = 3.0


def main():
    runs = pd.read_csv("results/tidy_runs.csv")
    elbow = pd.read_csv("results/elbow_table.csv")
    s0 = runs[runs.scenario == "S0"].dropna(subset=["p99_ms"])

    print()
    print(BAR)
    print("CALIBRATION VERDICT")
    print(BAR)

    if s0.empty:
        print("FAIL: no S0 runs with a p99 were ingested.")
        return 1

    prov = "SYNTHETIC" if runs["synthetic"].any() else "MEASURED"
    g = s0.groupby("load_rps")[["p50_ms", "p99_ms"]].median().sort_index()
    print(f"provenance: {prov}   ({len(s0)} S0 runs over {len(g)} load levels)")
    print()
    print("  offered r/s |    p50 ms |    p99 ms")
    print("  ------------+-----------+----------")
    for load, row in g.iterrows():
        print(f"  {load:>11.0f} | {row.p50_ms:>9.2f} | {row.p99_ms:>9.2f}")
    print()

    if prov != "MEASURED":
        print("FAIL: these are SYNTHETIC runs. lambda* must come from measured data.")
        print("      Clear results/ of synthetic files and re-run `make calibrate`.")
        return 1

    row = elbow[elbow.scenario == "S0"]
    op = float(row.op_elbow_rps.iloc[0]) if len(row) else float("nan")
    baseline = float(row.baseline_p99.iloc[0]) if len(row) else float("nan")

    lo_load = g.index[0]
    lo = g.iloc[0]
    lo_saturated = lo.p99_ms > SATURATED_RATIO * lo.p50_ms

    # elbow.py's baseline band: the lowest third of the grid (p99[:len//3]).
    band_n = max(1, len(g) // 3)
    band = g.iloc[:band_n]
    dirty = band[band.p99_ms > SATURATED_RATIO * band.p50_ms]

    # --- grid started past the elbow ------------------------------------------
    if lo_saturated:
        print(f"FAIL: the grid starts PAST the elbow. At the lowest load tested "
              f"({lo_load:.0f} r/s)")
        print(f"      p99={lo.p99_ms:.1f} ms is already {lo.p99_ms / max(lo.p50_ms, 1e-9):.1f}x "
              f"p50={lo.p50_ms:.1f} ms, i.e. the")
        print("      queue is building at the baseline itself. Any crossing found here")
        print("      measures how deep into overload the grid ran, not the elbow.")
        print()
        print("      Fix: LOWER APP_BUSINESS_CPU_MS in compose/scenarios/*.env, or extend")
        print(f"      the grid downward, e.g.  make calibrate LOADS=\"5 10 20 30 40 "
              f"{int(lo_load)}\"")
        print("      then re-run `make calibrate`.")
        return 1

    # --- baseline band contaminated --------------------------------------------
    if len(dirty):
        worst = dirty.iloc[-1]
        print("FAIL: the p99 BASELINE is contaminated. elbow.py averages the lowest")
        print(f"      third of the grid ({', '.join(f'{int(x)}' for x in band.index)} r/s) "
              f"to get its baseline, but")
        for load, r in dirty.iterrows():
            print(f"      {load:.0f} r/s is already queueing: p99={r.p99_ms:.1f} ms = "
                  f"{r.p99_ms / max(r.p50_ms, 1e-9):.1f}x p50={r.p50_ms:.1f} ms")
        print(f"      An inflated baseline ({baseline:.1f} ms) raises the 2x threshold with")
        print("      it, so the reported elbow lands at too HIGH a load.")
        print()
        print("      Fix: add resolution BELOW the knee so the baseline is drawn from")
        print("      genuinely idle points, e.g.")
        print(f"        make calibrate LOADS=\"{int(lo_load)} {int(lo_load * 1.5)} "
              f"{int(lo_load * 2)} {int(worst.name)} ...\"")
        print("      then re-run `make calibrate`.")
        return 1

    # --- elbow never reached ---------------------------------------------------
    if pd.isna(op):
        hi = g.index[-1]
        print(f"FAIL: no elbow in the tested range. p99 never exceeded 2x the low-load")
        print(f"      baseline ({2 * baseline:.2f} ms) all the way up to {hi:.0f} r/s —")
        print("      the service never saturated, so there is no lambda* to measure.")
        print()
        print("      Fix: RAISE APP_BUSINESS_CPU_MS in compose/scenarios/*.env (it is")
        print("      currently 12; try 24), or extend the grid upward, then re-run")
        print("      `make calibrate`.")
        return 1

    # --- success ---------------------------------------------------------------
    path = "results/lambda_star.txt"
    written = open(path).read().strip() if os.path.exists(path) else "(missing)"
    print(f"low-load p99 baseline : {baseline:.2f} ms   (2x threshold = {2 * baseline:.2f} ms)")
    print(f"first load with p99 > 2x baseline")
    print()
    print(f"    MEASURED lambda*  =  {op:.0f} req/s      -> {path} (holds: {written})")
    print()
    print("PASS: lambda* is measured from real S0 data on this machine.")
    print("      Next:  make rate-limits     (sets NGINX_RATE from this lambda*)")
    print("             make all-compose     (the real sweep)")
    print("             make check           (PASS/FAIL on the finished sweep)")
    print(BAR)
    return 0


if __name__ == "__main__":
    sys.exit(main())

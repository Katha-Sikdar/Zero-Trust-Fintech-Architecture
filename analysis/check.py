"""One-screen PASS/FAIL on a finished sweep. Names the check that failed.

  (a) PROVENANCE  ingest reports MEASURED, not SYNTHETIC.
  (b) FPR         benign false-positive rate < 2% throughout the OPERATING
                  ENVELOPE, i.e. at every load level up to and including
                  1.0 x lambda*, for every scenario. The last run failed here:
                  the gateway limiter was shedding legitimate load, nginx
                  returned 429, and scoring.py counts a non-2xx benign response
                  as a false positive (~50% FPR).

                  ABOVE lambda* the rate is reported but not failed on, because
                  past the elbow benign degradation is the phenomenon under
                  study rather than a misconfiguration, and it has two legitimate
                  causes: S6/S6fo hold a deliberately tight adaptive limit that
                  is MEANT to bind past the elbow (that is the reported result),
                  and every scenario driven beyond capacity sheds or times out
                  benign work by definition -- that is the Stability Gap. The
                  distinction that matters is that NOTHING false-positives while
                  the system is inside its envelope.
  (c) PATTERN     the expected enforcement pattern:
                    S0    blocks nothing, at any load
                    S4    blocks API2/API8 but NOT API1/API5/A10 (JWT alone
                          cannot make an authorization decision)
                    S5,S6 block API1/API5/A10 as well
                    S6fo  A10 block rate DROPS at 1.5x lambda* (the load-induced
                          fail-open bypass, OWASP A10:2025)

Run via `make check`, which runs the full analysis first.
"""
import os, subprocess, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FPR_MAX = 0.02      # (b) benign false-positive rate ceiling
HI = 0.80           # (c) "blocks this risk"
LO = 0.05           # (c) "does not block this risk"
DROP = 0.10         # (c) minimum absolute fall in S6fo A10 block rate at 1.5x
BAR = "=" * 74

fails: list[str] = []
notes: list[str] = []


def fail(check, msg):
    fails.append(f"[{check}] {msg}")


def near(series, target):
    """The load_norm level in `series` closest to `target`, or None."""
    vals = np.unique(series.dropna().values)
    return float(min(vals, key=lambda v: abs(v - target))) if len(vals) else None


def at(cells, scn, level, risk=None):
    sub = cells[(cells.scenario == scn) & np.isclose(cells.load_norm, level)]
    if risk is not None:
        sub = sub[sub.risk == risk]
    return sub


def block_rate(sub):
    tp, fn = sub.tp.sum(), sub.fn.sum()
    return tp / (tp + fn) if (tp + fn) else np.nan


def fpr(sub):
    fp, tn = sub.fp.sum(), sub.tn.sum()
    return fp / (fp + tn) if (fp + tn) else np.nan


# ---------------------------------------------------------------- (a) provenance
def check_provenance(_=None):
    r = subprocess.run([sys.executable, "analysis/ingest.py"],
                       capture_output=True, text=True)
    line = (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else ""
    if r.returncode != 0:
        fail("a PROVENANCE", f"ingest refused to run: {line}")
        return "REFUSED"
    kind = "MEASURED" if "[MEASURED]" in line else "SYNTHETIC" if "[SYNTHETIC]" in line else "?"
    if kind != "MEASURED":
        fail("a PROVENANCE", f"ingest reports {kind}, not MEASURED — "
                             "results/ holds invented data, not a real sweep.")
    return kind


# ----------------------------------------------------------------------- (b) FPR
def check_fpr(cells, elbow_lvl):
    rows = []
    for scn in sorted(cells.scenario.unique()):
        for lvl in sorted(cells[cells.scenario == scn].load_norm.unique()):
            v = fpr(at(cells, scn, lvl))
            if np.isnan(v):
                continue
            # Inside the operating envelope: at or below lambda*. The small
            # tolerance absorbs the rounding in load_rps = round(level * lambda*).
            in_envelope = lvl <= 1.0 + 1e-6
            rows.append(dict(scenario=scn, load_norm=lvl, fpr=v,
                             in_envelope=in_envelope))
    tab = pd.DataFrame(rows)
    if tab.empty:
        fail("b FPR", "no benign requests recorded — nothing to measure FPR on.")
        return tab

    for _, r in tab[tab.in_envelope & (tab.fpr >= FPR_MAX)].iterrows():
        fail("b FPR", f"{r.scenario} at load={r.load_norm:.2f}x lambda* — inside the "
                      f"operating envelope — has benign FPR {100 * r.fpr:.1f}% "
                      f">= {100 * FPR_MAX:.0f}%")
    for _, r in tab[~tab.in_envelope & (tab.fpr >= FPR_MAX)].iterrows():
        why = ("adaptive limit binding past the elbow, by design"
               if r.scenario in ("S6", "S6fo") else
               "driven past capacity: benign work sheds or times out (Stability Gap)")
        notes.append(f"{r.scenario} FPR {100 * r.fpr:.1f}% at {r.load_norm:.2f}x "
                     f"lambda* — above the envelope, not failed on: {why}")
    return tab


# ------------------------------------------------------------------- (c) pattern
def check_pattern(cells, elbow_lvl):
    present = set(cells.scenario.unique())

    def need(scn):
        if scn not in present:
            fail("c PATTERN", f"scenario {scn} is missing from results/ — "
                              "the sweep is incomplete.")
            return False
        return True

    # S0: blocks nothing, at every load level
    if need("S0"):
        for lvl in sorted(cells[cells.scenario == "S0"].load_norm.unique()):
            br = block_rate(at(cells, "S0", lvl))
            if not np.isnan(br) and br > LO:
                fail("c PATTERN", f"S0 blocks {100 * br:.1f}% of attacks at "
                                  f"{lvl:.2f}x lambda* — baseline must block ~0.")

    # S4: JWT only -> catches auth/misconfig, cannot catch authorization
    if need("S4"):
        for risk, want_hi in (("API2", True), ("API8", True),
                              ("API1", False), ("API5", False), ("A10", False)):
            br = block_rate(at(cells, "S4", elbow_lvl, risk))
            if np.isnan(br):
                fail("c PATTERN", f"S4 has no {risk} data at the elbow.")
            elif want_hi and br < HI:
                fail("c PATTERN", f"S4 {risk} block rate {br:.2f} < {HI} — "
                                  "sidecar JWT should block this.")
            elif not want_hi and br > LO:
                fail("c PATTERN", f"S4 {risk} block rate {br:.2f} > {LO} — "
                                  "JWT alone must NOT make this authorization call.")

    # S5/S6: JWT + OPA -> authorization risks covered too
    for scn in ("S5", "S6"):
        if not need(scn):
            continue
        for risk in ("API2", "API8", "API1", "API5", "A10"):
            br = block_rate(at(cells, scn, elbow_lvl, risk))
            if np.isnan(br):
                fail("c PATTERN", f"{scn} has no {risk} data at the elbow.")
            elif br < HI:
                fail("c PATTERN", f"{scn} {risk} block rate {br:.2f} < {HI} — "
                                  "JWT+OPA should block this.")

    # S6fo: fail-open collapses under load
    if need("S6fo"):
        hi_lvl = near(cells[cells.scenario == "S6fo"].load_norm, 1.5)
        b1 = block_rate(at(cells, "S6fo", elbow_lvl, "A10"))
        b15 = block_rate(at(cells, "S6fo", hi_lvl, "A10")) if hi_lvl else np.nan
        if np.isnan(b1) or np.isnan(b15):
            fail("c PATTERN", "S6fo A10 block rate is missing at the elbow or at 1.5x.")
        elif not (b1 - b15) >= DROP:
            fail("c PATTERN", f"S6fo A10 block rate did not drop at 1.5x lambda*: "
                              f"{b1:.2f} -> {b15:.2f} (need a fall of >= {DROP:.2f}).")
        else:
            notes.append(f"S6fo A10 block rate {b1:.2f} -> {b15:.2f} from "
                         f"{elbow_lvl:.2f}x to {hi_lvl:.2f}x lambda* (fail-open bypass)")


# ----------------------------------------------------------------------- report
def main():
    # Provenance first: it re-runs ingest, which rewrites the tidy CSVs. Reading
    # them before that would judge the previous pass's normalisation.
    kind = check_provenance(None)
    for f in ("results/tidy_runs.csv", "results/tidy_cells.csv"):
        if not os.path.exists(f):
            print(f"FAIL: {f} missing — run `make analyse` (or `make check`) on a "
                  "finished sweep.")
            return 1
    runs = pd.read_csv("results/tidy_runs.csv")
    cells = pd.read_csv("results/tidy_cells.csv")
    lstar = (open("results/lambda_star.txt").read().strip()
             if os.path.exists("results/lambda_star.txt") else "MISSING")
    mp = "results/lambda_star.measured.txt"
    if os.path.exists(mp):
        measured = open(mp).read().strip()
        if measured != lstar:
            notes.append(f"lambda* has drifted since calibration: measured {measured} "
                         f"-> now {lstar} r/s (elbow.py rewrites it from S6). The rate "
                         "limits were derived from the calibrated value; re-run "
                         "`make rate-limits` and the sweep if you want them to track this.")

    elbow_lvl = near(cells.load_norm, 1.0)
    if elbow_lvl is None:
        print("FAIL: no load levels ingested.")
        return 1
    fpr_tab = check_fpr(cells, elbow_lvl)
    check_pattern(cells, elbow_lvl)

    print()
    print(BAR)
    print(f"RUN CHECK    lambda* = {lstar} r/s    provenance = {kind}    "
          f"{len(runs)} runs, {sorted(runs.scenario.unique())}")
    print(BAR)

    if not fpr_tab.empty:
        piv = fpr_tab.pivot_table(index="scenario", columns="load_norm", values="fpr")
        print("benign FPR % by scenario x load/lambda*   "
              f"(ceiling {100 * FPR_MAX:.0f}% up to 1.00x; above that, reported only)")
        hdr = "  " + "scenario".ljust(9) + "".join(f"{c:>9.2f}" for c in piv.columns)
        print(hdr)
        for scn, row in piv.iterrows():
            cellstr = "".join("        ." if np.isnan(v) else f"{100 * v:>8.2f}"
                              + ("*" if v >= FPR_MAX else " ") for v in row.values)
            print("  " + str(scn).ljust(9) + cellstr)
        print("  (* = at or above the 2% ceiling)")
    print()

    for n in notes:
        print(f"  note: {n}")
    if notes:
        print()

    if fails:
        print(f"RESULT: FAIL — {len(fails)} check(s) failed")
        for f in fails:
            print(f"  FAIL {f}")
    else:
        print("RESULT: PASS")
        print(f"  a PROVENANCE  ingest reports MEASURED")
        print(f"  b FPR         benign false-positive rate < {100 * FPR_MAX:.0f}% at every "
              "load up to 1.00x lambda*, every scenario")
        print(f"  c PATTERN     S0 blocks nothing; S4 blocks API2/API8 only; "
              "S5/S6 also block API1/API5/A10;")
        print(f"                S6fo A10 collapses at 1.5x lambda*")
    print(BAR)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

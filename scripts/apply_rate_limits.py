"""Set NGINX_RATE in the scenario env-files as a function of the MEASURED lambda*.

The last run was invalid because the gateway limiter was shedding legitimate
load: nginx answers 429, loadgen/lib/scoring.js scores a non-2xx benign response
as a false positive, and benign FPR came out near 50%. The limiter must therefore
sit far enough above the offered load that it only sheds genuine floods.

  * Rate-limited scenarios  -> ceil(1.5 * lambda*) to the next 10 r/s.
    The sweep's top level is exactly 1.5 * lambda* (scripts/run-sweep.sh LEVELS),
    so rounding UP is deliberate: a limit that lands below the highest offered
    load would shed benign traffic at that level and reintroduce the very bug
    this is fixing.
  * S6 / S6fo -> ~1.10 * lambda*, i.e. the MIDPOINT between sweep levels 1.0 and
    1.2, rounded up to 5 and forced strictly above lambda*.
    S6 is the adaptive-limit arm: its limit is *meant* to bind just past the
    elbow, which is the result being reported. But it must not bind AT the elbow
    -- load level 1.0 is the reference point every table is read at, and a limit
    sitting on it would shed benign traffic there and fail the FPR check for a
    rounding reason rather than a real one. Rounding to 5 (not 10) keeps the
    limit inside the gap between sweep level 1.0 and level 1.2, which is what
    "tight, near lambda*" has to mean for the arm to say anything.
    S6fo carries the identical limit because it is the fail-open twin of S6 --
    differing limits would confound the fail-open comparison with a rate-limit
    difference.
  * S0/S1/S2 -> untouched. These are the no-limiter arms (NGINX_RATE=100000);
    S0rl exists precisely to be the baseline *with* the limiter.

NGINX_BURST scales with the rate, and must. nginx's limit_req admits a burst of
N requests ABOVE the rate before it sheds anything, so the burst sets how long an
overload runs unthrottled: roughly N / (offered - rate) seconds. The old files
paired burst=400 with rate=200-260, i.e. ~1.5x the rate. Leaving burst at 400
while the rate falls to lambda*-scale would make it 7x the rate -- S6 at 1.2x
lambda* would absorb the entire 45 s run inside the burst and never shed a single
request, so the "deliberately tighter adaptive limit" arm would measure nothing
at all. Holding burst at ~1.5x the rate preserves the limiter's original
character at the new scale.

Usage: python3 scripts/apply_rate_limits.py [--dry-run]
"""
import math, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN_DIR = os.path.join(ROOT, "compose", "scenarios")
LSTAR_PATH = os.path.join(ROOT, "results", "lambda_star.txt")

# scenarios whose limiter should only shed genuine floods
FLOOD_ONLY = ["S0rl", "S3", "S3off", "S4", "S4es", "S5"]
# scenarios that deliberately keep a tight, model-driven limit near lambda*
ADAPTIVE = ["S6", "S6fo"]
# no limiter at all -- left exactly as they are
UNLIMITED = ["S0", "S1", "S2"]

MARKER = "# NGINX_RATE derived"


def read_lambda_star():
    if not os.path.exists(LSTAR_PATH):
        raise SystemExit(
            f"no {os.path.relpath(LSTAR_PATH, ROOT)} — run `make calibrate` first.\n"
            "Rate limits must be derived from a MEASURED lambda*, not a guessed one.")
    txt = open(LSTAR_PATH).read().strip()
    try:
        lstar = float(txt)
    except ValueError:
        raise SystemExit(f"{LSTAR_PATH} does not hold a number: {txt!r}")
    if not lstar > 0:
        raise SystemExit(f"lambda* must be positive, got {lstar}")
    return lstar


def set_rate(path, rate, burst, note, dry_run):
    with open(path) as f:
        lines = f.read().splitlines()
    out, done = [], False
    for line in lines:
        if line.startswith(MARKER):
            continue                       # drop the previous derivation note
        if line.startswith("NGINX_RATE="):
            out.append(f"{MARKER} {note}")
            out.append(f"NGINX_RATE={rate}")
            done = True
            continue
        if line.startswith("NGINX_BURST="):
            out.append(f"NGINX_BURST={burst}")
            continue
        out.append(line)
    if not done:
        raise SystemExit(f"{path}: no NGINX_RATE= line to set")
    text = "\n".join(out) + "\n"
    if not dry_run:
        with open(path, "w") as f:
            f.write(text)
    return text


def main():
    dry_run = "--dry-run" in sys.argv
    lstar = read_lambda_star()

    flood = int(math.ceil(1.5 * lstar / 10.0) * 10)          # round UP to next 10
    # midpoint of the 1.0-1.2 gap, to nearest 5 up, never at or below lambda*
    adaptive = max(int(math.ceil(1.10 * lstar / 5.0) * 5), int(math.floor(lstar)) + 5)
    # burst ~1.5x rate, the ratio the original files used (400 against 260)
    burst = lambda r: max(10, int(round(1.5 * r / 10.0) * 10))

    print(f"measured lambda* = {lstar:g} r/s   (from results/lambda_star.txt)")
    print(f"  flood-only limit  = ceil(1.5 x lambda*)  -> {flood} r/s  "
          f"({flood / lstar:.2f} x lambda*)")
    print(f"  adaptive limit    = ~1.10 x lambda*      -> {adaptive} r/s  "
          f"({adaptive / lstar:.2f} x lambda*, binds between sweep levels 1.0 and 1.2)")
    print()

    for scn in FLOOD_ONLY:
        p = os.path.join(SCEN_DIR, f"{scn}.env")
        set_rate(p, flood, burst(flood),
                 f"from measured lambda*={lstar:g}: 1.5 x lambda*, rounded up to 10 r/s, "
                 f"burst ~1.5x rate. Sheds floods, not benign load.", dry_run)
        print(f"  {scn:<6} NGINX_RATE={flood:<6} NGINX_BURST={burst(flood)}")
    for scn in ADAPTIVE:
        p = os.path.join(SCEN_DIR, f"{scn}.env")
        set_rate(p, adaptive, burst(adaptive),
                 f"from measured lambda*={lstar:g}: model-driven adaptive limit held near "
                 f"lambda* (deliberately tighter), burst ~1.5x rate.", dry_run)
        print(f"  {scn:<6} NGINX_RATE={adaptive:<6} NGINX_BURST={burst(adaptive)}"
              f"   (adaptive, near lambda*)")
    for scn in UNLIMITED:
        print(f"  {scn:<6} unchanged (no limiter arm)")

    if dry_run:
        print("\n(dry run — nothing written)")
    else:
        print(f"\nwrote {len(FLOOD_ONLY) + len(ADAPTIVE)} scenario env-files. "
              "Re-run the sweep for these to take effect.")


if __name__ == "__main__":
    main()

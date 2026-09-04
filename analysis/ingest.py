"""Load every results/summary_*.json (real k6 output OR synthetic) into two tidy
tables: one row per (scenario, load, trial) for latency, and one row per
(scenario, load, trial, risk) for the confusion matrix. Writes CSVs used by the
rest of the pipeline.

PROVENANCE GUARD. Synthetic runs carry `"synthetic": true`; real k6 runs have no
such field. A directory holding both kinds cannot yield an honest result -- every
downstream number (lambda*, block rates, FPR, the elbow that drives the sweep)
would silently blend measured and invented data with no way to tell which is
which in the output. So a mixed directory is refused outright rather than
ingested with a warning. Synthetic corpora belong in results/synthetic-archive/,
which is never globbed here (glob is non-recursive by design).
"""
import glob, json, os, re, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import RISKS

# Directories that must never be ingested, only kept.
QUARANTINE = ("synthetic-archive", "example-output", "calibration")


def classify(results="results"):
    """Split the ingestable summaries into (real, synthetic) path lists.

    Only the top level of `results` is scanned: glob() does not recurse, so
    results/synthetic-archive/ and results/example-output/ are out of reach.
    """
    real, synth = [], []
    for path in sorted(glob.glob(os.path.join(results, "summary_*.json"))):
        if os.path.basename(os.path.dirname(path)) in QUARANTINE:
            continue                      # belt and braces; glob cannot reach these
        try:
            with open(path) as f:
                d = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise SystemExit(f"REFUSING TO INGEST: {path} is not readable JSON ({e}).")
        (synth if bool(d.get("synthetic", False)) else real).append(path)
    return real, synth


def guard(results="results"):
    """Refuse to ingest a directory that mixes measured and synthetic runs."""
    real, synth = classify(results)
    if real and synth:
        def sample(paths):
            return "".join(f"\n    {p}" for p in paths[:5]) + \
                   (f"\n    ... and {len(paths) - 5} more" if len(paths) > 5 else "")
        raise SystemExit(
            "REFUSING TO INGEST: {d}/ mixes measured and synthetic runs.\n"
            "  {ns} synthetic (have \"synthetic\": true):{ss}\n"
            "  {nr} measured  (no \"synthetic\" field):{rs}\n\n"
            "Every downstream number -- lambda*, block rates, FPR -- would blend the\n"
            "two with no way to tell them apart in the output. Move the synthetic\n"
            "files to {d}/synthetic-archive/ (never ingested), or clear the measured\n"
            "ones, then re-run. `make calibrate` and `make clean` both leave the\n"
            "archive untouched.".format(d=results, ns=len(synth), ss=sample(synth),
                                        nr=len(real), rs=sample(real)))
    return real, synth


def load(results="results"):
    real, synth = guard(results)          # exactly one of these is non-empty
    paths = sorted(real + synth)
    runs, cells = [], []
    for path in paths:
        with open(path) as f:
            d = json.load(f)
        trial = d.get("trial")
        if trial is None:
            m = re.search(r"_t(\d+)\.json$", path)
            trial = int(m.group(1)) if m else 1
        runs.append(dict(
            scenario=d["scenario"], load_rps=d["load_rps"], jwt_alg=d.get("jwt_alg", "RS256"),
            trial=trial, synthetic=bool(d.get("synthetic", False)),
            p50_ms=d.get("p50_ms"), p95_ms=d.get("p95_ms"), p99_ms=d.get("p99_ms"),
            http_reqs=d.get("http_reqs"), dropped=d.get("dropped_iterations", 0),
        ))
        for r, cm in d.get("matrix", {}).items():
            cells.append(dict(
                scenario=d["scenario"], load_rps=d["load_rps"], jwt_alg=d.get("jwt_alg", "RS256"),
                trial=trial, risk=r,
                tp=cm.get("tp", 0), fp=cm.get("fp", 0), tn=cm.get("tn", 0), fn=cm.get("fn", 0),
                block_rate=cm.get("block_rate"), fpr=cm.get("false_positive_rate"),
                attacks_sent=cm.get("attacks_sent", 0), benign_sent=cm.get("benign_sent", 0),
            ))
    runs = pd.DataFrame(runs)
    cells = pd.DataFrame(cells)
    if runs.empty:
        raise SystemExit("no results found — run analysis/synth/generate.py or a real sweep first")
    # attach the per-scenario lambda* so a normalized load axis is available
    lstar = 220
    p = os.path.join(results, "lambda_star.txt")
    if os.path.exists(p):
        lstar = float(open(p).read().strip())
    runs["load_norm"] = runs["load_rps"] / lstar
    cells["load_norm"] = cells["load_rps"] / lstar
    return runs, cells

if __name__ == "__main__":
    runs, cells = load()
    os.makedirs("results", exist_ok=True)
    runs.to_csv("results/tidy_runs.csv", index=False)
    cells.to_csv("results/tidy_cells.csv", index=False)
    kind = "SYNTHETIC" if runs["synthetic"].any() else "MEASURED"
    print(f"ingested {len(runs)} runs / {len(cells)} risk-cells [{kind}] "
          f"-> results/tidy_runs.csv, results/tidy_cells.csv")

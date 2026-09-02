"""Load every results/summary_*.json (real k6 output OR synthetic) into two tidy
tables: one row per (scenario, load, trial) for latency, and one row per
(scenario, load, trial, risk) for the confusion matrix. Writes CSVs used by the
rest of the pipeline."""
import glob, json, os, re, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import RISKS

def load(results="results"):
    runs, cells = [], []
    for path in sorted(glob.glob(os.path.join(results, "summary_*.json"))):
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
    kind = "SYNTHETIC" if runs["synthetic"].any() else "measured"
    print(f"ingested {len(runs)} runs / {len(cells)} risk-cells [{kind}] "
          f"-> results/tidy_runs.csv, results/tidy_cells.csv")

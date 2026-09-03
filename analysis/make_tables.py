"""Emit the paper's result tables (markdown + CSV) from ingested data."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    runs = pd.read_csv("results/tidy_runs.csv")
    cells = pd.read_csv("results/tidy_cells.csv")
    target = min(cells.load_norm.unique(), key=lambda x: abs(x-1.0))

    # Table: coverage + cost per scenario near the elbow
    rows=[]
    # Baseline is S0rl (no enforcement, but the SAME gateway rate limit as
    # S3-S5), not S0. S0 admits all offered load while the enforcement scenarios
    # shed at 200 r/s, so a delta against S0 measures the limiter, not the
    # enforcement point. S0/S1/S2 are unlimited and their delta is not comparable.
    base = runs[(runs.scenario=="S0rl")]
    if base.empty:
        base = runs[(runs.scenario=="S0")]
    base_p99 = base[np.isclose(base.load_norm,target)]["p99_ms"].median()
    for scn in ["S0","S0rl","S1","S2","S3","S3off","S4","S4es","S5","S6","S6fo"]:
        rr=runs[(runs.scenario==scn)&(np.isclose(runs.load_norm,target))]
        cc=cells[(cells.scenario==scn)&(np.isclose(cells.load_norm,target))]
        if rr.empty: continue
        n=cc.tp.sum()+cc.fn.sum()
        rows.append(dict(scenario=scn,
            p50_ms=round(rr.p50_ms.median(),2), p99_ms=round(rr.p99_ms.median(),2),
            added_p99_ms=round(rr.p99_ms.median()-base_p99,2),   # signed: may be negative
            coverage_pct=round(100*cc.tp.sum()/max(1,n),1),
            fpr_pct=round(100*cc.fp.sum()/max(1,(cc.fp.sum()+cc.tn.sum())),2)))
    t=pd.DataFrame(rows)
    t.to_csv("results/table_coverage_cost.csv", index=False)

    md=["# Result Tables", "",
        f"_Load level: ~{target:.1f} x lambda*. "
        f"{'SYNTHETIC illustrative data.' if runs.get('synthetic',pd.Series([False])).any() else 'Measured data.'}_","",
        "## Coverage vs cost per scenario","",
        "| scenario | p50 ms | p99 ms | added p99 | coverage % | FPR % |",
        "|---|---|---|---|---|---|"]
    for _,r in t.iterrows():
        md.append(f"| {r.scenario} | {r.p50_ms} | {r.p99_ms} | {r.added_p99_ms} | {r.coverage_pct} | {r.fpr_pct} |")
    md.append("")

    # per-scenario confusion matrix
    md += ["## Confusion matrix per scenario (summed over risks, near elbow)","",
           "| scenario | TP | FP | TN | FN | block rate | FPR |","|---|---|---|---|---|---|---|"]
    for scn in ["S0","S0rl","S3","S3off","S4","S4es","S5","S6","S6fo"]:
        cc=cells[(cells.scenario==scn)&(np.isclose(cells.load_norm,target))]
        if cc.empty: continue
        tp,fp,tn,fn=cc.tp.sum(),cc.fp.sum(),cc.tn.sum(),cc.fn.sum()
        br=tp/max(1,(tp+fn)); fpr=fp/max(1,(fp+tn))
        md.append(f"| {scn} | {tp} | {fp} | {tn} | {fn} | {br:.3f} | {fpr:.3f} |")
    open("results/tables.md","w").write("\n".join(md))
    print("wrote results/tables.md and results/table_coverage_cost.csv")

if __name__ == "__main__":
    main()

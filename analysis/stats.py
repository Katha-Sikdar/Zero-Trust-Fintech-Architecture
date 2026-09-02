"""
Statistical analysis (proposal Section 6.4).

  * Latency (continuous): one-way ANOVA across scenarios at a fixed load level,
    plus targeted Welch t-tests with Cohen's d effect sizes for the two paired
    contrasts the RQs name — S3 vs S4 (application vs sidecar JWT offloading,
    RQ1) and S4 vs S4es (RS256 vs ES256, RQ2).
  * Block rate (binomial): Wilson score intervals per scenario/risk, and Fisher
    exact tests comparing enforcement configurations (e.g. S4 vs S5 on BOLA).
Effect sizes are reported alongside every p-value so significance from large
k6 sample counts is not mistaken for practical importance.
Outputs a markdown report and supporting CSVs.
"""
import os, sys, math
import numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import RISKS

def wilson(k, n, z=1.96):
    if n == 0: return (None, None, None)
    p = k / n
    denom = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denom
    half = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / denom
    return (p, max(0, centre-half), min(1, centre+half))

def cohen_d(a, b):
    a, b = np.asarray(a), np.asarray(b)
    na, nb = len(a), len(b)
    sp = math.sqrt(((na-1)*a.var(ddof=1) + (nb-1)*b.var(ddof=1)) / max(1, na+nb-2))
    return (a.mean() - b.mean()) / sp if sp else 0.0

def at_elbow_slice(runs):
    lvl = runs["load_norm"].unique()
    target = lvl[np.argmin(np.abs(lvl - 1.0))]
    return runs[np.isclose(runs["load_norm"], target)]

def main():
    runs = pd.read_csv("results/tidy_runs.csv")
    cells = pd.read_csv("results/tidy_cells.csv")
    out = ["# Statistical Analysis", ""]
    kind = "SYNTHETIC (illustrative)" if runs.get("synthetic", pd.Series([False])).any() else "measured"
    out += [f"_Data: **{kind}**._", ""]

    at_elbow = at_elbow_slice(runs)
    lvl = at_elbow["load_norm"].iloc[0] if not at_elbow.empty else None

    # ---- ANOVA on p99 across core scenarios at the elbow ----
    groups, labels = [], []
    for scn in ["S0","S1","S2","S3","S4","S5","S6"]:
        v = at_elbow[at_elbow.scenario == scn]["p99_ms"].dropna().values
        if len(v) > 1: groups.append(v); labels.append(scn)
    out += ["## 1. Latency across scenarios (p99, at load ~ lambda*)", ""]
    if len(groups) >= 2:
        F, p = stats.f_oneway(*groups)
        grand = np.concatenate(groups)
        ss_between = sum(len(g)*(g.mean()-grand.mean())**2 for g in groups)
        ss_total = ((grand-grand.mean())**2).sum()
        eta2 = ss_between/ss_total if ss_total else 0
        out += [f"One-way ANOVA across {', '.join(labels)} at load_norm={lvl:.2f}:",
                f"- F = {F:.2f}, p = {p:.2e}, eta^2 = {eta2:.3f} "
                f"({'large' if eta2>0.14 else 'medium' if eta2>0.06 else 'small'} effect)", ""]

    # ---- paired contrasts ----
    def contrast(a, b, title, rq):
        va = at_elbow[at_elbow.scenario == a]["p99_ms"].dropna().values
        vb = at_elbow[at_elbow.scenario == b]["p99_ms"].dropna().values
        if len(va) < 2 or len(vb) < 2:
            return [f"### {title}", "_insufficient data_", ""]
        t, p = stats.ttest_ind(va, vb, equal_var=False)
        d = cohen_d(va, vb)
        return [f"### {title}  ({rq})",
                f"- {a}: mean p99 = {va.mean():.2f} ms (n={len(va)}); "
                f"{b}: mean p99 = {vb.mean():.2f} ms (n={len(vb)})",
                f"- Welch t = {t:.2f}, p = {p:.2e}, Cohen's d = {d:.2f} "
                f"({'large' if abs(d)>0.8 else 'medium' if abs(d)>0.5 else 'small'})", ""]
    out += ["## 2. Targeted contrasts", ""]
    out += contrast("S3", "S4", "Application-layer vs sidecar JWT", "RQ1")
    out += contrast("S4", "S4es", "RS256 vs ES256 at the sidecar", "RQ2")

    # ---- block-rate Wilson intervals + Fisher contrast ----
    out += ["## 3. Security efficacy (block rate, Wilson 95% CI)", "",
            "| scenario | risk | block rate | 95% CI | attacks |",
            "|---|---|---|---|---|"]
    agg = cells.groupby(["scenario","risk"]).agg(tp=("tp","sum"), fn=("fn","sum")).reset_index()
    for _, r in agg.iterrows():
        if r.scenario not in ["S0","S3","S4","S5","S6","S6fo"]: continue
        n = r.tp + r.fn
        p, lo, hi = wilson(r.tp, n)
        if p is None: continue
        out.append(f"| {r.scenario} | {r.risk} | {p:.3f} | [{lo:.3f}, {hi:.3f}] | {n} |")
    out.append("")

    # BOLA coverage: sidecar-JWT-only (S4) vs +OPA (S5)
    out += ["## 4. Does authorization offloading matter? (Fisher exact, API1/BOLA)", ""]
    def cell(scn, risk):
        s = cells[(cells.scenario==scn)&(cells.risk==risk)]
        return int(s.tp.sum()), int(s.fn.sum())
    tp4, fn4 = cell("S4","API1"); tp5, fn5 = cell("S5","API1")
    if (tp4+fn4) and (tp5+fn5):
        odds, p = stats.fisher_exact([[tp5, fn5],[tp4, fn4]])
        out += [f"- S4 (JWT only) BOLA block rate = {tp4/(tp4+fn4):.3f}",
                f"- S5 (JWT+OPA) BOLA block rate = {tp5/(tp5+fn5):.3f}",
                f"- Fisher exact p = {p:.2e} (odds ratio {odds:.1f}) — "
                f"JWT offloading alone does not cover authorization.", ""]

    # ---- RQ5: fail-open vs fail-closed past the elbow ----
    out += ["## 5. RQ5 — enforcement past lambda* (fail-open vs fail-closed)", "",
            "| load/lambda* | S6 A10 block | S6fo A10 block |","|---|---|---|"]
    for ln in sorted(cells.load_norm.unique()):
        def br(scn):
            s = cells[(cells.scenario==scn)&(cells.risk=="A10")&(np.isclose(cells.load_norm,ln))]
            n = s.tp.sum()+s.fn.sum(); return s.tp.sum()/n if n else float("nan")
        out.append(f"| {ln:.2f} | {br('S6'):.3f} | {br('S6fo'):.3f} |")
    out += ["", "_A collapse in the S6fo column past load/lambda*=1.0 is the "
            "load-induced enforcement bypass (OWASP A10:2025)._", ""]

    os.makedirs("results", exist_ok=True)
    open("results/stats_report.md","w").write("\n".join(out))
    agg.to_csv("results/block_rates.csv", index=False)
    print("wrote results/stats_report.md and results/block_rates.csv")

if __name__ == "__main__":
    main()

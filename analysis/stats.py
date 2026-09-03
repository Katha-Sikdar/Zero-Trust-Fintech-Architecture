"""
Statistical analysis (proposal Section 6.4).

  * Latency (continuous): one-way ANOVA across scenarios at a fixed load level,
    plus targeted Welch t-tests with Cohen's d effect sizes for the two paired
    contrasts the RQs name — S3 vs S4 (application vs sidecar JWT offloading,
    RQ1) and S4 vs S4es (RS256 vs ES256, RQ2).
  * Block rate (binomial): the independent unit is the TRIAL, not the request.
    Requests within one k6 run share a process, a warmed JIT, a connection pool
    and a queue state, so pooling ~10^4 requests per cell and treating them as
    one binomial sample understates the variance by the design effect and drives
    p-values toward zero for reasons unrelated to the effect. Every rate here is
    therefore computed per trial and summarised across trials: mean of per-trial
    rates with a t interval over trials, falling back to the exact Clopper-Pearson
    limit on the trial count when a cell is degenerate (every trial identical).
    Configuration contrasts use Mann-Whitney U on the per-trial rates rather than
    Fisher's exact test on pooled counts, for the same reason.
Effect sizes are reported alongside every p-value so significance from large
k6 sample counts is not mistaken for practical importance, and the family of
reported p-values is Holm-Bonferroni corrected.
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

def cluster_ci(rates, alpha=0.05):
    """95% CI for a proportion whose independent unit is the trial.

    rates: one block rate per trial. Returns (mean, lo, hi, method).
    With m trials the t interval on the trial means is the cluster-level
    analogue of a binomial CI. When every trial gives the same rate the sample
    variance is 0 and a t interval would claim zero width, so a degenerate cell
    at 0 or 1 is reported with the exact Clopper-Pearson bound on m trials
    (k=0 or k=m) -- the 'rule of three' generalisation, which stays honest about
    how little m trials can exclude.
    """
    r = np.asarray([x for x in rates if np.isfinite(x)], dtype=float)
    m = len(r)
    if m == 0: return (None, None, None, "no data")
    if m == 1: return (float(r[0]), None, None, "single trial")
    mean, sd = float(r.mean()), float(r.std(ddof=1))
    if sd > 0:
        half = stats.t.ppf(1 - alpha/2, m-1) * sd / math.sqrt(m)
        return (mean, max(0.0, mean-half), min(1.0, mean+half), f"t, m={m}")
    if mean in (0.0, 1.0):
        k = int(round(mean * m))
        lo = stats.beta.ppf(alpha/2, k, m-k+1) if k > 0 else 0.0
        hi = stats.beta.ppf(1-alpha/2, k+1, m-k) if k < m else 1.0
        return (mean, float(lo), float(hi), f"Clopper-Pearson, m={m}")
    # identical non-boundary trials: the data supports no width claim, and a
    # zero-width interval would assert precision the design cannot deliver.
    return (mean, None, None, f"degenerate: {m} identical trials")

def cohen_d(a, b):
    a, b = np.asarray(a), np.asarray(b)
    na, nb = len(a), len(b)
    sp = math.sqrt(((na-1)*a.var(ddof=1) + (nb-1)*b.var(ddof=1)) / max(1, na+nb-2))
    return (a.mean() - b.mean()) / sp if sp else 0.0

def rank_biserial(a, b):
    """Effect size for Mann-Whitney U: 2*U/(na*nb) - 1, in [-1, 1]."""
    a, b = np.asarray(a), np.asarray(b)
    if not len(a) or not len(b): return float("nan")
    U = stats.mannwhitneyu(a, b, alternative="two-sided").statistic
    return 2.0 * U / (len(a) * len(b)) - 1.0

def holm(pairs):
    """Holm-Bonferroni over [(label, p), ...] -> {label: (p_raw, p_adj)}."""
    valid = [(lab, p) for lab, p in pairs if p is not None and np.isfinite(p)]
    order = sorted(valid, key=lambda x: x[1])
    m, out, running = len(order), {}, 0.0
    for i, (lab, p) in enumerate(order):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)          # enforce monotonicity
        out[lab] = (p, running)
    return out

def at_elbow_slice(runs):
    lvl = runs["load_norm"].unique()
    target = lvl[np.argmin(np.abs(lvl - 1.0))]
    return runs[np.isclose(runs["load_norm"], target)]

def trial_rates(cells, scn, risk):
    """Per-trial block rate (tp / attacks) for one scenario+risk cell."""
    s = cells[(cells.scenario == scn) & (cells.risk == risk)]
    if s.empty: return np.array([])
    g = s.groupby("trial").agg(tp=("tp", "sum"), fn=("fn", "sum"))
    n = g.tp + g.fn
    return (g.tp[n > 0] / n[n > 0]).values

def main():
    runs = pd.read_csv("results/tidy_runs.csv")
    cells = pd.read_csv("results/tidy_cells.csv")
    out = ["# Statistical Analysis", ""]
    kind = "SYNTHETIC (illustrative)" if runs.get("synthetic", pd.Series([False])).any() else "measured"
    out += [f"_Data: **{kind}**._", "",
            "_The independent unit for every proportion below is the trial "
            "(one k6 run), not the individual request; requests within a run are "
            "not independent. Reported p-values are Holm-Bonferroni corrected "
            "across the family of tests in sections 1, 2 and 4._", ""]

    at_elbow = at_elbow_slice(runs)
    lvl = at_elbow["load_norm"].iloc[0] if not at_elbow.empty else None
    # the security tables are read at the same load level as the latency tests;
    # coverage is load-dependent (that is RQ5), so pooling across loads would
    # average away the very effect under study.
    cells_elbow = (cells[np.isclose(cells.load_norm, lvl)] if lvl is not None else cells)

    pvals = []   # (label, p) collected for Holm correction

    # ---- ANOVA on p99 across core scenarios at the elbow ----
    groups, labels = [], []
    for scn in ["S0","S1","S2","S3","S4","S5","S6"]:
        v = at_elbow[at_elbow.scenario == scn]["p99_ms"].dropna().values
        if len(v) > 1: groups.append(v); labels.append(scn)
    out += ["## 1. Latency across scenarios (p99, at load ~ lambda*)", ""]
    anova = None
    if len(groups) >= 2:
        F, p = stats.f_oneway(*groups)
        grand = np.concatenate(groups)
        ss_between = sum(len(g)*(g.mean()-grand.mean())**2 for g in groups)
        ss_total = ((grand-grand.mean())**2).sum()
        eta2 = ss_between/ss_total if ss_total else 0
        anova = (F, p, eta2, labels, lvl)
        pvals.append(("ANOVA p99 across scenarios", p))
    else:
        out += ["_insufficient p99 data for an ANOVA "
                "(does k6 summaryTrendStats include 'p(99)'?)_", ""]

    # ---- paired contrasts ----
    contrasts = []
    def contrast(a, b, title, rq):
        va = at_elbow[at_elbow.scenario == a]["p99_ms"].dropna().values
        vb = at_elbow[at_elbow.scenario == b]["p99_ms"].dropna().values
        if len(va) < 2 or len(vb) < 2:
            contrasts.append((title, rq, a, b, va, vb, None, None, None)); return
        t, p = stats.ttest_ind(va, vb, equal_var=False)
        d = cohen_d(va, vb)
        contrasts.append((title, rq, a, b, va, vb, t, p, d))
        pvals.append((f"{a} vs {b} (p99)", p))
    contrast("S3", "S4", "Application-layer vs sidecar JWT", "RQ1")
    contrast("S4", "S4es", "RS256 vs ES256 at the sidecar", "RQ2")

    # ---- BOLA coverage: sidecar-JWT-only (S4) vs +OPA (S5), trial level ----
    r4 = trial_rates(cells_elbow, "S4", "API1")
    r5 = trial_rates(cells_elbow, "S5", "API1")
    bola = None
    if len(r4) >= 2 and len(r5) >= 2:
        U, p = stats.mannwhitneyu(r5, r4, alternative="two-sided")
        bola = (r4, r5, U, p, rank_biserial(r5, r4))
        pvals.append(("S4 vs S5 BOLA block rate", p))

    adj = holm(pvals)
    def padj(label, p):
        if label in adj:
            return f"p = {p:.2e} (Holm-adjusted p = {adj[label][1]:.2e})"
        return f"p = {p:.2e}"

    # ---- render section 1 ----
    if anova:
        F, p, eta2, labels, lv = anova
        out += [f"One-way ANOVA across {', '.join(labels)} at load_norm={lv:.2f}:",
                f"- F = {F:.2f}, {padj('ANOVA p99 across scenarios', p)}, eta^2 = {eta2:.3f} "
                f"({'large' if eta2>0.14 else 'medium' if eta2>0.06 else 'small'} effect)",
                f"- n = {len(groups[0])} trials per scenario (independent runs)", ""]

    # ---- render section 2 ----
    out += ["## 2. Targeted contrasts", ""]
    for title, rq, a, b, va, vb, t, p, d in contrasts:
        out += [f"### {title}  ({rq})"]
        if t is None:
            out += ["_insufficient data_", ""]; continue
        out += [f"- {a}: mean p99 = {va.mean():.2f} ms (n={len(va)} trials); "
                f"{b}: mean p99 = {vb.mean():.2f} ms (n={len(vb)} trials)",
                f"- Welch t = {t:.2f}, {padj(f'{a} vs {b} (p99)', p)}, Cohen's d = {d:.2f} "
                f"({'large' if abs(d)>0.8 else 'medium' if abs(d)>0.5 else 'small'})", ""]

    # ---- block-rate CIs over trials ----
    lvl_txt = f"load_norm={lvl:.2f}" if lvl is not None else "all loads"
    out += [f"## 3. Security efficacy (block rate, 95% CI over trials, {lvl_txt})", "",
            "| scenario | risk | block rate | 95% CI | trials | attacks | CI method |",
            "|---|---|---|---|---|---|---|"]
    ci_rows = []
    for scn in ["S0","S0rl","S3","S3off","S4","S4es","S5","S6","S6fo","S6oc","S6fooc"]:
        for risk in RISKS:
            rates = trial_rates(cells_elbow, scn, risk)
            if not len(rates): continue
            mean, lo, hi, method = cluster_ci(rates)
            s = cells_elbow[(cells_elbow.scenario == scn) & (cells_elbow.risk == risk)]
            attacks = int(s.tp.sum() + s.fn.sum())
            ci = f"[{lo:.3f}, {hi:.3f}]" if lo is not None else "n/a"
            out.append(f"| {scn} | {risk} | {mean:.3f} | {ci} | {len(rates)} | {attacks} | {method} |")
            ci_rows.append(dict(scenario=scn, risk=risk, block_rate=mean, ci_lo=lo, ci_hi=hi,
                                n_trials=len(rates), attacks_sent=attacks, ci_method=method))
    out += ["", "_The CI is over trials, so it widens with the number of repeated "
            "runs, not with the number of requests fired._", ""]

    # ---- render section 4 ----
    out += ["## 4. Does authorization offloading matter? (API1/BOLA, trial level)", ""]
    if bola is None:
        out += ["_insufficient data_", ""]
    else:
        r4, r5, U, p, rb = bola
        m4, l4, h4, _ = cluster_ci(r4)
        m5, l5, h5, _ = cluster_ci(r5)
        out += [f"- S4 (JWT only) BOLA block rate = {m4:.3f} "
                f"[{l4:.3f}, {h4:.3f}] over {len(r4)} trials",
                f"- S5 (JWT+OPA) BOLA block rate = {m5:.3f} "
                f"[{l5:.3f}, {h5:.3f}] over {len(r5)} trials",
                f"- Mann-Whitney U = {U:.0f}, {padj('S4 vs S5 BOLA block rate', p)}, "
                f"rank-biserial r = {rb:.2f} — JWT offloading alone does not cover "
                "authorization.", ""]

    # ---- RQ5: fail-open vs fail-closed past the elbow ----
    out += ["## 5. RQ5 — enforcement past lambda* (fail-open vs fail-closed)", "",
            "| load/lambda* | S6 A10 block [95% CI] | S6fo A10 block [95% CI] |","|---|---|---|"]
    for ln in sorted(cells.load_norm.unique()):
        def br(scn):
            sub = cells[np.isclose(cells.load_norm, ln)]
            rates = trial_rates(sub, scn, "A10")
            if not len(rates): return "n/a"
            mean, lo, hi, _ = cluster_ci(rates)
            return f"{mean:.3f} [{lo:.3f}, {hi:.3f}]" if lo is not None else f"{mean:.3f}"
        out.append(f"| {ln:.2f} | {br('S6')} | {br('S6fo')} |")
    out += ["", "_A collapse in the S6fo column past load/lambda*=1.0 is the "
            "load-induced enforcement bypass (OWASP A10:2025)._", ""]

    os.makedirs("results", exist_ok=True)
    open("results/stats_report.md","w").write("\n".join(out))
    pd.DataFrame(ci_rows).to_csv("results/block_rates.csv", index=False)
    print("wrote results/stats_report.md and results/block_rates.csv")

if __name__ == "__main__":
    main()

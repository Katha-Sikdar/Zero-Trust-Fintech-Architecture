"""Regenerate the proposal's result figures from ingested data (real or
synthetic). Saves PNGs to results/figures/. Colours/labels match the proposal."""
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SCENARIO_LABELS

ACC="#2E4A7D"; RED="#A93B21"; GRN="#1D6B57"; AMB="#9C6412"; GREY="#6E7787"; LINE="#C3CCD8"
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.edgecolor":"#5A6473",
                     "axes.linewidth":0.9,"figure.dpi":150})
OUT="results/figures"; os.makedirs(OUT, exist_ok=True)

def load():
    return pd.read_csv("results/tidy_runs.csv"), pd.read_csv("results/tidy_cells.csv")

def synthetic_stamp(fig, runs):
    if runs.get("synthetic", pd.Series([False])).any():
        fig.text(0.99, 0.01, "SYNTHETIC DATA", ha="right", va="bottom",
                 fontsize=7, color=RED, alpha=0.7)

# ---- Fig A: latency elbow, key scenarios ----
def fig_elbow(runs):
    fig, ax = plt.subplots(figsize=(6,3.6))
    for scn,c in [("S0",ACC),("S3",AMB),("S4",GRN),("S6",RED)]:
        g = runs[runs.scenario==scn].groupby("load_rps")["p99_ms"]
        m, sd = g.median(), g.std()
        if m.empty: continue
        ax.plot(m.index, m.values, color=c, lw=2, label=f"{scn} {SCENARIO_LABELS.get(scn,'')}")
        ax.fill_between(m.index, m.values-sd.values, m.values+sd.values, color=c, alpha=0.12)
    ax.set_xlabel("Offered load (requests/second)"); ax.set_ylabel("p99 latency (ms)")
    ax.legend(frameon=False, fontsize=8); ax.grid(color=LINE, lw=0.6, alpha=0.7); ax.set_axisbelow(True)
    ax.spines[["top","right"]].set_visible(False)
    synthetic_stamp(fig, runs); fig.tight_layout(); fig.savefig(f"{OUT}/figA_elbow.png"); plt.close(fig)

# ---- Fig B: RQ5 — fail-open vs fail-closed under an OPA control-plane outage ----
def fig_efficacy(runs, cells):
    """Under load alone the two policies are indistinguishable (the limiter sheds
    before OPA saturates), so the informative contrast is the outage arm."""
    # every arm read at the same load level: the outage arms were run at lambda*
    # only, so pooling the healthy arms over all five levels would not compare like
    # with like.
    tgt = min(cells.load_norm.unique(), key=lambda x: abs(x-1.0))
    cells = cells[np.isclose(cells.load_norm, tgt)]
    def rates(scn):
        s = cells[(cells.scenario == scn) & (cells.risk == "API1")]
        if s.empty: return None
        g = s.groupby("trial").agg(tp=("tp","sum"), fn=("fn","sum"),
                                   fp=("fp","sum"), tn=("tn","sum"))
        blk = (g.tp / (g.tp + g.fn).replace(0, np.nan)).mean()
        fpr = (g.fp / (g.fp + g.tn).replace(0, np.nan)).mean()
        return 100*blk, 100*fpr
    arms = [("S6","fail-closed\nOPA healthy"), ("S6fo","fail-open\nOPA healthy"),
            ("S6oc","fail-closed\nOPA DOWN"), ("S6fooc","fail-open\nOPA DOWN")]
    got = [(lab, rates(scn)) for scn, lab in arms]
    got = [(lab, r) for lab, r in got if r]
    if not got: return
    fig, ax = plt.subplots(figsize=(6.4,3.6))
    x = np.arange(len(got)); w = 0.38
    ax.bar(x - w/2, [r[0] for _, r in got], w, color=GRN, label="BOLA attacks blocked")
    ax.bar(x + w/2, [r[1] for _, r in got], w, color=RED, label="benign traffic denied (FPR)")
    for i, (_, r) in enumerate(got):
        ax.text(i - w/2, r[0] + 2, f"{r[0]:.0f}", ha="center", fontsize=8)
        ax.text(i + w/2, r[1] + 2, f"{r[1]:.0f}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels([lab for lab, _ in got], fontsize=8)
    ax.set_ylabel("percent"); ax.set_ylim(0, 118)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper left")
    ax.grid(axis="y", color=LINE, lw=0.6, alpha=0.7); ax.set_axisbelow(True)
    ax.spines[["top","right"]].set_visible(False)
    synthetic_stamp(fig, runs); fig.tight_layout()
    fig.savefig(f"{OUT}/figB_failopen.png"); plt.close(fig)

# ---- Fig C: security-performance frontier ----
def fig_frontier(runs, cells):
    """x is the SIGNED delta against S0rl (no enforcement, same rate limiter).
    Signed, because sidecar enforcement rejects bad traffic before the backend and
    can lower p99; matched, because a delta against unlimited S0 would measure the
    rate limiter rather than the enforcement point."""
    fig, ax = plt.subplots(figsize=(6.4,3.9))
    ref = runs[runs.scenario == "S0rl"]
    if ref.empty: ref = runs[runs.scenario == "S0"]
    tgt_ref = min(ref.load_norm.unique(), key=lambda x: abs(x-1.0))
    base = ref[np.isclose(ref.load_norm, tgt_ref)]["p99_ms"].median()
    pts = []
    for scn in ["S0","S0rl","S1","S2","S3","S3off","S4","S4es","S5","S6","S6fo"]:
        rr = runs[runs.scenario == scn]; cc = cells[cells.scenario == scn]
        if rr.empty or cc.empty: continue
        t = min(rr.load_norm.unique(), key=lambda x: abs(x-1.0))
        p99 = rr[np.isclose(rr.load_norm, t)]["p99_ms"].median()
        cov = cc[np.isclose(cc.load_norm, t)]
        coverage = 100*cov.tp.sum()/max(1,(cov.tp.sum()+cov.fn.sum()))
        pts.append((scn, p99 - base, coverage))
    # S2 (+150 ms) would compress every other point onto a single vertical line,
    # so it is drawn clamped at the right edge with its true value in the label.
    finite = [p[1] for p in pts if abs(p[1]) < 50]
    xmax = max(finite) + 3.5; xmin = min(finite) - 2.0
    off = {"S0":(7,4),"S0rl":(7,-11),"S1":(7,-11),"S3":(7,5),"S3off":(7,-11),
           "S4":(7,4),"S4es":(7,-11),"S5":(-30,7),"S6":(7,5),"S6fo":(7,-11)}
    for scn, x, y in pts:
        clipped = x > xmax
        xp = xmax if clipped else x
        c = RED if scn.startswith("S6") else GRN if scn.startswith(("S4","S5")) \
            else AMB if scn.startswith("S3") else ACC
        ax.scatter([xp], [y], s=54, color=c, zorder=3, edgecolor="white",
                   marker=">" if clipped else "o")
        lab = f"{scn} (+{x:.0f} ms)" if clipped else scn
        ax.annotate(lab, (xp, y), textcoords="offset points",
                    xytext=off.get(scn, (7,-3)), fontsize=8)
    ax.axvline(0, color=GREY, ls=":", lw=1)
    ax.text(0.15, 3, "no latency cost", color=GREY, fontsize=7.5, rotation=90, va="bottom")
    ax.set_xlim(xmin, xmax + 1.2)
    ax.set_xlabel(r"$\Delta$ p99 vs rate-limit-matched baseline S0rl (ms)")
    ax.set_ylabel("OWASP risk coverage (%)")
    ax.set_ylim(-6,106); ax.grid(color=LINE, lw=0.6, alpha=0.7); ax.set_axisbelow(True)
    ax.spines[["top","right"]].set_visible(False)
    synthetic_stamp(fig, runs); fig.tight_layout()
    fig.savefig(f"{OUT}/figC_frontier.png"); plt.close(fig)

# ---- Fig D: per-risk block rate by scenario (near elbow) ----
def fig_perrisk(runs, cells):
    scen=["S0","S0rl","S3","S3off","S4","S5","S6"]; risks=["API1","API2","API4","API5","API8","A10"]
    target = min(cells.load_norm.unique(), key=lambda x: abs(x-1.0))
    M=np.zeros((len(scen),len(risks)))
    for i,s in enumerate(scen):
        for j,r in enumerate(risks):
            d=cells[(cells.scenario==s)&(cells.risk==r)&(np.isclose(cells.load_norm,target))]
            n=d.tp.sum()+d.fn.sum(); M[i,j]=(d.tp.sum()/n) if n else 0
    fig, ax = plt.subplots(figsize=(6.4,3.4))
    im=ax.imshow(M, cmap="BuGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(risks))); ax.set_xticklabels(risks)
    ax.set_yticks(range(len(scen))); ax.set_yticklabels(scen)
    for i in range(len(scen)):
        for j in range(len(risks)):
            ax.text(j,i,f"{M[i,j]:.2f}",ha="center",va="center",
                    color="white" if M[i,j]>0.6 else "#333", fontsize=8)
    ax.set_title(f"Block rate by scenario x risk (load ~ {target:.1f} lambda*)", fontsize=9)
    fig.colorbar(im, ax=ax, shrink=0.8, label="block rate")
    synthetic_stamp(fig, runs); fig.tight_layout(); fig.savefig(f"{OUT}/figD_coverage_heatmap.png"); plt.close(fig)

def main():
    runs, cells = load()
    fig_elbow(runs); fig_efficacy(runs, cells); fig_frontier(runs, cells); fig_perrisk(runs, cells)
    print(f"wrote 4 figures to {OUT}/")

if __name__ == "__main__":
    main()

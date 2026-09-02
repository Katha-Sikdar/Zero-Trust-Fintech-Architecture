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

# ---- Fig B: efficacy under load (RQ5) — S6 vs S6fo block rate + p99 ----
def fig_efficacy(runs, cells):
    fig, ax = plt.subplots(figsize=(6,3.6))
    for scn,c,ls in [("S6",GRN,"-"),("S6fo",RED,"--")]:
        s = cells[(cells.scenario==scn)&(cells.risk=="A10")]
        if s.empty: continue
        g = s.groupby("load_norm").apply(lambda d: d.tp.sum()/max(1,(d.tp.sum()+d.fn.sum())))
        ax.plot(g.index, g.values*100, color=c, lw=2, ls=ls, marker="o", ms=4,
                label=f"{scn} A10 block rate")
    ax.axvline(1.0, color=GREY, ls=":", lw=1); ax.text(1.02, 8, r"$\lambda^{*}$", color=GREY)
    ax.axvspan(1.0, runs.load_norm.max(), color=RED, alpha=0.05)
    ax.set_xlabel(r"Offered load / $\lambda^{*}$"); ax.set_ylabel("A10 block rate (%)")
    ax.set_ylim(0,105); ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.grid(color=LINE, lw=0.6, alpha=0.7); ax.set_axisbelow(True); ax.spines[["top","right"]].set_visible(False)
    synthetic_stamp(fig, runs); fig.tight_layout(); fig.savefig(f"{OUT}/figB_failopen.png"); plt.close(fig)

# ---- Fig C: security-performance frontier ----
def fig_frontier(runs, cells):
    fig, ax = plt.subplots(figsize=(6,3.8))
    base_p99 = runs[(runs.scenario=="S0")].groupby("load_norm")["p99_ms"].median()
    pts=[]
    for scn in ["S0","S1","S2","S3","S4","S5","S6"]:
        rr = runs[(runs.scenario==scn)]
        cc = cells[(cells.scenario==scn)]
        if rr.empty or cc.empty: continue
        # near-elbow slice
        target = min(rr.load_norm.unique(), key=lambda x: abs(x-1.0))
        p99 = rr[np.isclose(rr.load_norm,target)]["p99_ms"].median()
        b = base_p99.get(target, base_p99.median())
        added = max(0.0, p99 - b)
        cov = cc[np.isclose(cc.load_norm,target)]
        coverage = 100*cov.tp.sum()/max(1,(cov.tp.sum()+cov.fn.sum()))
        pts.append((scn, added, coverage))
    for scn,x,y in pts:
        c = RED if scn=="S6" else GRN if scn in("S4","S5") else AMB if scn=="S3" else ACC
        ax.scatter([x],[y], s=52, color=c, zorder=3, edgecolor="white")
        ax.annotate(f"{scn}", (x,y), textcoords="offset points", xytext=(7,-3), fontsize=8)
    ax.set_xlabel("Added p99 over baseline (ms)"); ax.set_ylabel("OWASP risk coverage (%)")
    ax.set_ylim(-5,105); ax.grid(color=LINE, lw=0.6, alpha=0.7); ax.set_axisbelow(True)
    ax.spines[["top","right"]].set_visible(False)
    synthetic_stamp(fig, runs); fig.tight_layout(); fig.savefig(f"{OUT}/figC_frontier.png"); plt.close(fig)

# ---- Fig D: per-risk block rate by scenario (near elbow) ----
def fig_perrisk(runs, cells):
    scen=["S0","S3","S4","S5","S6"]; risks=["API1","API2","API4","API5","API8","A10"]
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

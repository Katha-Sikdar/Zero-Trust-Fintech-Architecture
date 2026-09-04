"""Run the whole analysis pipeline in order. Equivalent to `make analyse`."""
import subprocess, sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ingest runs TWICE, and the repeat is not redundant. ingest.py derives the
# normalised load axis (load_norm = load_rps / lambda*) from results/lambda_star.txt,
# but elbow.py is what WRITES that file. On the first pass ingest therefore
# normalises against whatever lambda* was left over -- or against the NOMINAL
# fallback when there is none -- and every downstream step keys off load_norm.
# Re-ingesting after the fit re-normalises against the lambda* actually measured.
steps = ["analysis/ingest.py", "analysis/elbow.py", "analysis/ingest.py",
         "analysis/stats.py", "analysis/make_tables.py", "analysis/figures.py",
         "analysis/make_latex.py"]
for s in steps:
    print(f"\n=== {s} ===", flush=True)   # flush: the children share this fd
    r = subprocess.run([sys.executable, s])
    if r.returncode != 0:
        sys.exit(f"step failed: {s}")
print("\nAnalysis complete. See results/ for CSVs, stats_report.md, tables.md, figures/.")

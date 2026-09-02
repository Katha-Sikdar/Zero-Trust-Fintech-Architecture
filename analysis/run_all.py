"""Run the whole analysis pipeline in order. Equivalent to `make analyse`."""
import subprocess, sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
steps = ["analysis/ingest.py", "analysis/elbow.py", "analysis/stats.py",
         "analysis/make_tables.py", "analysis/figures.py"]
for s in steps:
    print(f"\n=== {s} ===")
    r = subprocess.run([sys.executable, s])
    if r.returncode != 0:
        sys.exit(f"step failed: {s}")
print("\nAnalysis complete. See results/ for CSVs, stats_report.md, tables.md, figures/.")

"""Restore pinned GEO matrices, rerun the notebook, and regenerate the report."""

import csv
import json
import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[2]
study = root / "research/menthol-aerosol-single-cell"
spec_path = "research/menthol-aerosol-single-cell/report-spec.json"
with (study / "source_manifest.tsv").open() as stream:
    samples = list(csv.DictReader(stream, delimiter="\t"))
inputs = ["research/menthol-aerosol-single-cell/source_manifest.tsv"] + [
    f"research/menthol-aerosol-single-cell/data/{row['filename']}" for row in samples
]
artifacts = [f"research/menthol-aerosol-single-cell/results/{name}" for name in (
    "sample_qc.tsv", "marker_bins.tsv", "target_pseudobulk.tsv", "contrast_summary.tsv", "analysis_summary.json"
)]
commands = [
    [sys.executable, "restore-inputs.py", spec_path],
    [sys.executable, "research/menthol-aerosol-single-cell/build_notebook.py"],
    [sys.executable, "notebook-runner.py", "notebooks/gse263903_menthol_aerosol.ipynb", ".", "600", json.dumps(artifacts), json.dumps(inputs)],
    ["node", "report-generator.mjs", spec_path],
]
for command in commands:
    subprocess.run(command, cwd=root, check=True)

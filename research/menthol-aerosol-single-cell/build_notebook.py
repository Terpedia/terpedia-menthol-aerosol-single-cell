"""Build the inspectable GSE263903 analysis notebook from versioned source."""

from pathlib import Path

import nbformat


intro = """# GSE263903: menthol-mint aerosol single-cell audit

This notebook reads all ten public 10x filtered gene-count matrices: one male and one female library each for air, PG:VG vehicle, Mango, MentholMint, and Tobacco aerosol. The [paper](https://elifesciences.org/articles/106380) states that the flavored products contain nicotine and that two mice were pooled per sex and condition into each library. Collection dates differ by condition. There is no single-compound menthol arm or scRNA-seq nicotine-only arm.

The analysis reports per-library QC, broad **marker-enriched bins** derived from simple gene panels, and targeted pseudobulk expression within each bin. Bins are exploratory and are not validated cell-type annotations. Contrasts are sex-stratified descriptions of pooled libraries. They have no p-values and cannot isolate menthol, nicotine, aerosol chemistry, sex, collection date, or cell composition effects. Cell counts are not biological replicate counts.
"""

analysis = r'''from pathlib import Path
import hashlib
import json
import h5py
import numpy as np
import pandas as pd
from scipy.sparse import csc_matrix

ROOT = Path.cwd()
STUDY = ROOT / "research/menthol-aerosol-single-cell"
RESULTS = STUDY / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
manifest = pd.read_csv(STUDY / "source_manifest.tsv", sep="\t", dtype=str)
assert set(manifest.condition) == {"Air", "PGVG", "Mango", "MentholMint", "Tobacco"}
assert len(manifest) == 10

panels = {
    "Myeloid-marker": ["Lyz2", "Csf1r", "Adgre1", "Itgam", "S100a8"],
    "Lymphoid-marker": ["Cd3d", "Cd3e", "Ms4a1", "Nkg7", "Trbc2"],
    "Epithelial-marker": ["Epcam", "Krt18", "Scgb1a1", "Sftpc", "Krt8"],
    "Endothelial-marker": ["Pecam1", "Kdr", "Emcn", "Cdh5", "Vwf"],
    "Stromal-marker": ["Col1a1", "Dcn", "Pdgfra", "Col3a1", "Lum"],
}
targets = ["Il1b", "Il12b", "Nfkbia", "Cxcl2", "Hspa1a", "Hspa1b", "Hmgcr", "Sqle", "Fasn", "Acaca", "Trpm8"]
bins = list(panels) + ["Unassigned"]

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()

def summarize_library(row):
    path = STUDY / "data" / row.filename
    assert sha256(path) == row.sha256, f"Checksum mismatch: {row.gsm}"
    with h5py.File(path) as handle:
        group = handle["matrix"]
        names = [value.decode() for value in group["features/name"][:]]
        shape = tuple(int(value) for value in group["shape"][:])
        matrix = csc_matrix((group["data"][:], group["indices"][:], group["indptr"][:]), shape=shape)
    assert matrix.shape[0] == len(names)
    gene_index = {name: index for index, name in enumerate(names)}
    total = np.asarray(matrix.sum(axis=0)).ravel().astype(float)
    detected = np.diff(matrix.indptr)
    mito_rows = [i for i, name in enumerate(names) if name.lower().startswith("mt-")]
    mito = np.asarray(matrix[mito_rows, :].sum(axis=0)).ravel() / np.maximum(total, 1)
    keep = (total >= 500) & (detected >= 200) & (mito <= 0.20)

    scores = []
    for genes in panels.values():
        expression = [matrix.getrow(gene_index[gene]).toarray().ravel() for gene in genes if gene in gene_index]
        assert expression, "Missing all marker genes from a panel"
        scores.append(np.mean(np.log1p(np.asarray(expression) / np.maximum(total, 1) * 10_000), axis=0))
    scores = np.asarray(scores)
    labels = scores.argmax(axis=0)
    labels[scores.max(axis=0) < 0.15] = len(panels)
    qc = {"gsm": row.gsm, "condition": row.condition, "sex": row.sex, "sac_date": row.sac_date,
          "cells_raw": len(total), "cells_qc": int(keep.sum()), "genes_matrix": matrix.shape[0],
          "median_umi_qc": float(np.median(total[keep])) if keep.any() else None,
          "median_genes_qc": float(np.median(detected[keep])) if keep.any() else None,
          "median_mito_fraction_qc": float(np.median(mito[keep])) if keep.any() else None,
          "source_sha256": row.sha256}
    bin_rows, expression_rows = [], []
    for label_id, label in enumerate(bins):
        selected = keep & (labels == label_id)
        n_cells = int(selected.sum())
        library_umi = float(total[selected].sum())
        bin_rows.append({"gsm": row.gsm, "condition": row.condition, "sex": row.sex,
                         "marker_bin": label, "cells": n_cells, "fraction_qc_cells": n_cells / max(int(keep.sum()), 1)})
        for gene in targets:
            count = float(matrix.getrow(gene_index[gene]).toarray().ravel()[selected].sum()) if gene in gene_index else 0.0
            expression_rows.append({"gsm": row.gsm, "condition": row.condition, "sex": row.sex,
                                    "marker_bin": label, "gene": gene, "gene_present": gene in gene_index,
                                    "cells": n_cells, "gene_umis": count, "bin_umis": library_umi,
                                    "log2_cpm": float(np.log2((count + 0.5) / (library_umi + 1) * 1_000_000)) if n_cells >= 30 else np.nan})
    return qc, bin_rows, expression_rows

qc_rows, bin_rows, expression_rows = [], [], []
for row in manifest.itertuples(index=False):
    qc, one_bins, one_expression = summarize_library(row)
    qc_rows.append(qc)
    bin_rows.extend(one_bins)
    expression_rows.extend(one_expression)
    print(row.gsm, row.condition, row.sex, "QC cells", qc["cells_qc"])

sample_qc = pd.DataFrame(qc_rows)
marker_bins = pd.DataFrame(bin_rows)
target_pseudobulk = pd.DataFrame(expression_rows)
sample_qc.to_csv(RESULTS / "sample_qc.tsv", sep="\t", index=False)
marker_bins.to_csv(RESULTS / "marker_bins.tsv", sep="\t", index=False)
target_pseudobulk.to_csv(RESULTS / "target_pseudobulk.tsv", sep="\t", index=False)
display(sample_qc[["gsm", "condition", "sex", "sac_date", "cells_raw", "cells_qc", "median_umi_qc", "median_mito_fraction_qc"]])
'''

contrasts = r'''from itertools import product
comparisons = [("MentholMint", "PGVG"), ("MentholMint", "Air"),
               ("MentholMint", "Mango"), ("MentholMint", "Tobacco"),
               ("Mango", "PGVG"), ("Tobacco", "PGVG"), ("PGVG", "Air")]
indexed = target_pseudobulk.set_index(["condition", "sex", "marker_bin", "gene"])
contrast_rows = []
for treated, control in comparisons:
    for sex, marker_bin, gene in product(["Male", "Female"], bins, targets):
        a = indexed.loc[(treated, sex, marker_bin, gene)]
        b = indexed.loc[(control, sex, marker_bin, gene)]
        if not (a.gene_present and b.gene_present and np.isfinite(a.log2_cpm) and np.isfinite(b.log2_cpm)):
            continue
        contrast_rows.append({"treated": treated, "control": control, "sex": sex,
                              "marker_bin": marker_bin, "gene": gene,
                              "treated_cells": int(a.cells), "control_cells": int(b.cells),
                              "treated_log2_cpm": float(a.log2_cpm), "control_log2_cpm": float(b.log2_cpm),
                              "delta_log2_cpm": float(a.log2_cpm - b.log2_cpm)})
contrast_summary = pd.DataFrame(contrast_rows)
contrast_summary.to_csv(RESULTS / "contrast_summary.tsv", sep="\t", index=False)
myeloid = contrast_summary[(contrast_summary.marker_bin == "Myeloid-marker") &
                           (contrast_summary.treated == "MentholMint")]
display(myeloid.pivot_table(index=["control", "gene"], columns="sex", values="delta_log2_cpm").round(2))

summary = {
    "source_accession": "GSE263903", "library_count": len(manifest),
    "qc_cells_total": int(sample_qc.cells_qc.sum()),
    "qc_thresholds": {"min_umi": 500, "min_detected_genes": 200, "max_mito_fraction": 0.20},
    "marker_bin_method": "Highest mean log1p(CP10K) across five marker genes; unassigned below 0.15; exploratory, not validated cell types",
    "target_method": "Pooled raw UMI counts per marker bin and library; log2((gene_UMI + 0.5)/(bin_UMI + 1)*1e6)",
    "comparison_method": "Within-sex difference of library-level log2 CPM; descriptive only; no p-values",
    "limits": ["Each library pools two mice of one sex; cells are not independent biological replicates.",
               "The flavored aerosols contain tobacco-derived nicotine and other constituents; the scRNA-seq set has no nicotine-only control.",
               "GEO collection dates differ by condition, so date and treatment are confounded.",
               "Marker-enriched bins are not validated cell-type annotations or differential-expression estimates."]
}
(RESULTS / "analysis_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
'''

notebook = nbformat.v4.new_notebook(cells=[
    nbformat.v4.new_markdown_cell(intro),
    nbformat.v4.new_code_cell(analysis),
    nbformat.v4.new_markdown_cell("## Sex-stratified descriptive contrasts\n\nThe contrasts below compare pooled libraries from different collection dates. Sign agreement across male and female libraries is a descriptive check and must not be called biological replication or a menthol-specific effect."),
    nbformat.v4.new_code_cell(contrasts),
])
notebook.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
notebook.metadata["language_info"] = {"name": "python"}
output = Path(__file__).resolve().parents[2] / "notebooks" / "gse263903_menthol_aerosol.ipynb"
nbformat.write(notebook, output)
print(output)

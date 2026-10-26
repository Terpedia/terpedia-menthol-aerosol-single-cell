"""Build the source-linked Terputer report specification for GSE263903."""

import csv
import json
from pathlib import Path


root = Path(__file__).resolve().parents[2]
study = root / "research/menthol-aerosol-single-cell"
with (study / "source_manifest.tsv").open() as stream:
    rows = list(csv.DictReader(stream, delimiter="\t"))

spec = {
    "schema_version": 2,
    "slug": "menthol-aerosol-single-cell",
    "title": "A compact single-cell audit of a menthol-mint e-cigarette aerosol arm in mouse lung",
    "question": "Which metabolic and signaling responses to terpene exposure are reproducible, and which depend on cellular context or a specific target?",
    "notebook": "notebooks/gse263903_menthol_aerosol.ipynb",
    "execution_receipt": "research/execution-receipts/gse263903_menthol_aerosol.json",
    "data_inputs": [
        {"path": f"research/menthol-aerosol-single-cell/data/{row['filename']}",
         "url": row["source_url"], "sha256": row["sha256"]}
        for row in rows
    ],
    "sources": [
        {"id": "geo", "title": "NCBI GEO series GSE263903 and sample records", "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE263903"},
        {"id": "paper", "title": "Kaur et al., eLife 2026, single-cell flavored e-cigarette aerosol study", "url": "https://elifesciences.org/articles/106380"},
    ],
    "claims": [
        {"id": "C01", "class": "source-reported", "text": "GSE263903 contains mouse-lung single-cell libraries for air, PG:VG, mango, menthol-mint, and tobacco aerosol conditions. This audit selects the two sex-labeled libraries per air, PG:VG, and menthol-mint condition. The paper states that each library pools two mice of one sex, and that the flavored e-liquids contain tobacco-derived nicotine.", "sources": ["geo", "paper"], "limitation": "The GEO library is the measurable unit here; individual mouse variation cannot be recovered from pooled cells. The menthol-mint product is a mixture, not an isolated menthol exposure."},
        {"id": "C02", "class": "observed", "text": "The six selected filtered 10x matrices contain 39,608 barcodes; 37,962 pass this notebook's minimum 500 UMI, 200 detected genes, and at most 20% mitochondrial UMI thresholds. The male PG:VG library retains 2,451 cells, versus 7,199 to 7,771 in the air and menthol-mint libraries.", "sources": ["geo"], "artifacts": ["research/menthol-aerosol-single-cell/results/sample_qc.tsv", "research/menthol-aerosol-single-cell/results/analysis_summary.json"], "limitation": "These are QC counts from already filtered 10x matrices using this notebook's thresholds; they do not reproduce the paper's cell filtering or cell-type annotations. Capture differences can distort apparent composition."},
        {"id": "C03", "class": "observed", "text": "The exploratory myeloid-marker bin comprises 15.8% of retained male PG:VG cells and 21.9% of retained male menthol-mint cells; the corresponding female fractions are 14.7% and 18.0%.", "sources": ["geo"], "artifacts": ["research/menthol-aerosol-single-cell/results/marker_bins.tsv"], "limitation": "The bins use five marker genes and are not validated cell types. Sex pools, collection date, capture, and cell-state mixtures remain confounded."},
        {"id": "C04", "class": "observed", "text": "Within the myeloid-marker bin, menthol-mint versus PG:VG log2 CPM differences for Il1b are +1.65 in the male library and +1.46 in the female library; for Cxcl2 they are +1.43 and +1.19, respectively.", "sources": ["geo"], "artifacts": ["research/menthol-aerosol-single-cell/results/contrast_summary.tsv", "research/menthol-aerosol-single-cell/results/target_pseudobulk.tsv"], "limitation": "These are pooled-library descriptions, not differential-expression estimates or independent biological replications. Changes in the marker-bin mixture can affect pseudobulk abundance."},
        {"id": "C05", "class": "observed", "text": "The control choice changes the descriptive contrast: against air, female myeloid-bin Il1b and Cxcl2 differences are only +0.19 and +0.21 log2 CPM, compared with +1.46 and +1.19 against PG:VG.", "sources": ["geo"], "artifacts": ["research/menthol-aerosol-single-cell/results/contrast_summary.tsv"], "limitation": "Air and PG:VG have distinct exposure and collection dates. A smaller contrast to air does not identify which aerosol component caused a response."},
        {"id": "C06", "class": "observed", "text": "In the same targeted myeloid-bin panel, Hmgcr differs by +0.07 log2 CPM in the male library and -0.13 in the female library for menthol-mint versus PG:VG; this audit does not identify a consistent Hmgcr direction across the two sex pools.", "sources": ["geo"], "artifacts": ["research/menthol-aerosol-single-cell/results/contrast_summary.tsv"], "limitation": "One targeted gene is not a pathway analysis. The design cannot distinguish exposure effects from sex and date effects."},
        {"id": "C07", "class": "source-reported", "text": "The paper reports flavor-dependent aerosol metal levels and a nicotine-only control for selected follow-up assays, but GEO's ten single-cell libraries do not contain a nicotine-only scRNA-seq arm. GEO records the selected PG:VG, air, and menthol-mint library collection dates as October 20, October 21, and November 11, 2022.", "sources": ["geo", "paper"], "limitation": "Treatment and collection date are confounded in these archived libraries; the study cannot isolate a menthol-specific transcriptional effect."},
        {"id": "C08", "class": "proposed", "text": "A discriminating follow-up would randomize independent mice across collection days and compare vehicle, nicotine-only, purified menthol, menthol plus nicotine, and matched aerosol controls within each sex. Analyze validated cell types using mouse-level pseudobulk and include measured aerosol chemistry and exposure dose.", "sources": ["geo", "paper"], "limitation": "This experiment is proposed only; no such data were generated or analyzed here."},
    ],
    "abstract": ["C01", "C02", "C04", "C05", "C07"],
    "sections": {
        "background": ["C01", "C07"],
        "methods": ["C02", "C03"],
        "results": ["C02", "C03", "C04", "C05", "C06"],
        "interpretation": ["C04", "C05", "C06"],
        "limitations": ["C01", "C02", "C03", "C04", "C05", "C06", "C07"],
        "next_steps": ["C08"],
    },
}
(study / "report-spec.json").write_text(json.dumps(spec, indent=2) + "\n")
print(study / "report-spec.json")

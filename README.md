# GSE263903 menthol-mint aerosol single-cell audit

This project applies the Terputer report pipeline to all ten public mouse-lung 10x libraries from [GSE263903](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE263903). It includes an [executed Jupyter notebook](notebooks/gse263903_menthol_aerosol.ipynb), a [claim-linked white paper](research/menthol-aerosol-single-cell/generated/white-paper.md), [ledger](research/menthol-aerosol-single-cell/generated/claim-ledger.tsv), and [hash receipts](research/menthol-aerosol-single-cell/generated/generation-receipt.json).

The libraries cover air, PG:VG vehicle, Mango, MentholMint, and Tobacco flavored e-cigarette aerosol, with one male and one female library per condition. The [published study](https://elifesciences.org/articles/106380) states that each library pools two mice of one sex; the flavored products contain nicotine. GEO records different collection dates for the conditions. This is a **mixed-aerosol, descriptive analysis**. It cannot isolate menthol, assign target engagement, or estimate independent mouse-level differential expression.

The notebook retains 74,117 cells under its stated QC thresholds. Its simple marker-enriched bins and targeted pseudobulk summaries are exploratory. In the myeloid-marker bin, `Il1b` and `Cxcl2` are higher in both MentholMint sex pools than in the corresponding PG:VG pools. The female comparisons against air are much smaller, comparisons against Mango are smaller in both pools, and comparisons against Tobacco change sign between sex pools. These results demonstrate control sensitivity and motivate a balanced follow-up; they do not establish a reproducible menthol-specific pathway.

## Reproduce

Use Python 3.12 and Node.js. The ten 10x matrices are omitted from Git because they total about 319 MB; their GEO URLs and SHA-256 hashes are pinned in the [source manifest](research/menthol-aerosol-single-cell/source_manifest.tsv) and [report specification](research/menthol-aerosol-single-cell/report-spec.json).

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python research/menthol-aerosol-single-cell/reproduce.py
```

`reproduce.py` restores and checks the ten matrices, rebuilds and executes the notebook in a fresh kernel, records artifact and input hashes, then regenerates the report. A new execution timestamp changes the receipt hash even when numerical results agree. Review the notebook, [sample QC](research/menthol-aerosol-single-cell/results/sample_qc.tsv), and [contrast table](research/menthol-aerosol-single-cell/results/contrast_summary.tsv) before interpreting a result.

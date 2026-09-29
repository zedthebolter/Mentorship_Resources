# Reproducibility code

This anonymized package contains the code and non-identifying aggregate data
used to inspect and recreate the main reported results for a manuscript under
double-blind peer review.

The package reproduces public aggregate tables, matching-balance checks,
diagnostics, and manuscript Figures 2–4 from saved statistical outputs. It does
not contain individual mentor–mentee records or the upstream code used to
construct those records.

## Files

```text
.
├── README.md
├── requirements.txt
├── Main_Analysis_and_Figures.ipynb
├── Data/
│   ├── README.md
│   ├── main_table3_spearman.csv
│   ├── main_table3_spearman_audit.csv
│   ├── figure2_panel_a_standardized_means.csv
│   ├── group_distribution_summary.csv
│   ├── kde_density_curves.csv
│   ├── psm_run_summary.csv
│   ├── psm_balance.csv
│   ├── psm_effects.csv
│   ├── regression_coefficients.csv
│   ├── regression_diagnostics.csv
│   ├── sample_flow.csv
│   ├── vif_diagnostics.csv
│   └── additional aggregate table and audit files
└── Figure/
    └── generated PDF and PNG figures
```

`Data/README.md` provides a file-by-file description of every included CSV.

## Data

All files in `Data/` contain non-identifying aggregate data or saved model
outputs. They include:

- the displayed and audited Spearman correlations for Main Table 3;
- standardized group means and density-curve coordinates for Figure 2;
- propensity-score-matching estimates and balance diagnostics;
- saved regression coefficients and model diagnostics;
- sample-construction, descriptive-statistics, and VIF outputs.

Raw Academic Family Tree and OpenAlex records are not included. The package
also excludes PairID-level analytical files, author and mentor identifiers,
identity-linkage code, mentor-inference code, upstream data-construction code,
exploratory notebooks, and manuscript or presentation generation scripts.

Re-estimating the models from individual mentor–mentee records is outside the
scope of this review package because the linked records contain persistent
identifiers and are subject to source-data licensing and re-identification
constraints.

## Environment

The notebook was saved with Python 3.13. The required Python packages and
minimum versions are listed in `requirements.txt`.

```bash
python -m venv .venv
```

Activate the virtual environment using the command appropriate for the local
operating system:

```bash
# macOS or Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install the dependencies and start Jupyter:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
jupyter lab
```

## Run order

Run all commands from the repository root. Open
`Main_Analysis_and_Figures.ipynb` and execute all cells from top to bottom.
The notebook uses relative paths and does not require editing local paths.

The notebook performs the following steps in order:

1. inventories the included CSV files;
2. displays Main Table 3 and its statistical audit;
3. verifies that every released matching run has a maximum absolute
   post-matching standardized mean difference below 0.10;
4. recreates manuscript Figures 2–4;
5. displays regression diagnostics, sample-flow summaries, and VIF results.

The generated files are:

```text
Figure/
├── figure2_group_profiles.png
├── figure2_group_profiles.pdf
├── figure3_resource_results.png
├── figure3_resource_results.pdf
├── figure4_landmark_results.png
└── figure4_landmark_results.pdf
```

Figure 2 contains the group profiles and distributional comparisons. Figure 3
contains the matching and two-part-model results. Figure 4 contains the
landmark and continuity results.

## Reproducibility boundary

This package supports inspection and recreation of the reported aggregate
results. It does not reproduce the upstream linkage, sample construction, or
model estimation from individual records. A permanent public repository will
be provided after the double-blind peer-review process.

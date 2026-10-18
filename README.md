# Academic mentorship analysis

This anonymized package contains mentor–mentee indicator data, analysis code,
statistical outputs and an executed notebook for double-blind peer review.
The analyses use two-year (t2) and three-year (t3) publication lags. Main figures
use t3; corresponding t2 figures are also included.

## Files

```text
.
├── README.md
├── requirements.txt
├── Main_Analysis_and_Figures.ipynb
├── Code/
│   ├── run_analysis.py
│   ├── analysis_engine.py
│   ├── export_tables.py
│   ├── figure_inputs.py
│   ├── make_figures.py
│   ├── make_group_figure.py
│   ├── test_matching.py
│   └── Upstream/
├── Data/
│   ├── README.md
│   ├── dataset_manifest.csv
│   └── 12 compressed indicator tables
├── Results/
│   ├── README.md
│   ├── Supplementary_Tables.md
│   └── statistical outputs and supplementary table panels
└── Figure/
    ├── captions.md
    ├── t3/  (Figures 2–4, PNG and PDF)
    └── t2/  (Figures 3–4, PNG and PDF)
```

## Data

Each row represents a mentor–mentee relationship spell in one observation
window. Anonymous identifiers are consistent across tables. The twelve tables
cover 5-, 10- and 20-year, overall-career, and two landmark windows under each
lag. Samples overlap and should not be summed. Variable definitions are in
`Data/README.md`; file names, row counts and checksums are in
`Data/dataset_manifest.csv`.

Mentorship data: [Ke et al. (2022)](https://doi.org/10.1038/s41597-022-01578-x),
[Zenodo](https://doi.org/10.5281/zenodo.4917086).
Publication metadata: May 30, 2025 OpenAlex snapshot.

## Run

Use Python 3.13. From the package root:

```bash
python -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\Activate.ps1` in Windows PowerShell, then run:

```bash
python -m pip install -r requirements.txt
jupyter lab
```

Open `Main_Analysis_and_Figures.ipynb` and run all cells in order to estimate the
models, format Tables S1–S13 and generate Figures 2–4. All paths are relative
to the package root. The equivalent command-line entry point is:

```bash
python Code/run_analysis.py --workers 2
```

To redraw Figures 3–4 from saved estimates:

```bash
python Code/make_figures.py
```

## Outputs

`Results/README.md` lists the statistical output files. Tables S1–S4 describe
the samples and variables; S5–S9 report conventional-window analyses;
S10–S13 report landmark analyses. Figure captions and display units are in
`Figure/captions.md`.

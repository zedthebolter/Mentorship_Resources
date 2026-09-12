# Mentorship resources and citation-elite journal publication trajectories after training: Evidence from bioscience mentor-mentee networks

This directory is the public data-and-code package for the manuscript. Its
organization follows a compact reproducibility format: one Jupyter notebook,
one folder of non-identifying processed data, and one output folder for
figures.

## Contents

- `Main_Analysis_and_Figures.ipynb` reads the released CSV files, displays the
  main correlation table, checks propensity-score-matching balance, and
  recreates descriptive, matching, regression, and landmark result figures.
- `Data/` contains only non-identifying aggregate data and saved statistical
  outputs. See `Data/README.md` for a file-by-file description.
- `Figure/` is the local output directory created by the notebook. Generated
  PDF and PNG files are ignored by Git.

## Run

Create a Python environment and install the small set of dependencies:

```bash
python -m pip install -r requirements.txt
jupyter lab
```

Open `Main_Analysis_and_Figures.ipynb` and run all cells from top to bottom.
The notebook uses paths relative to its own directory; no local path needs to
be edited.

## Public-release boundary

This package does not include raw Academic Family Tree or OpenAlex data,
author or mentor identifiers, PairID-level analytical files, identity-linkage
code, mentor-inference code, upstream data-construction code, exploratory
notebooks, or Word/SI/PPT generation and QA scripts.

The released model-output files allow readers to inspect and recreate the
reported aggregate results. Re-estimating the models from individual
mentor--mentee records requires controlled-access research data and is outside
this public package.

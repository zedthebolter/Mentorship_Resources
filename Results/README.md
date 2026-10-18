# Statistical outputs

| File | Contents |
|---|---|
| Supplementary_Tables.md | Formatted supplementary tables S1–S13 |
| supplementary_tables.json | The same table headers, cells and notes in structured form |
| S1A.csv through S13C.csv, as applicable | Individual supplementary table panels |
| regression_coefficients.csv | Focal and control coefficients, clustered standard errors, p-values and confidence intervals |
| regression_diagnostics.csv | Model sample sizes, convergence, AIC and PPML Pearson dispersion |
| vif_diagnostics.csv | Predictor VIFs and corresponding sample sizes |
| sample_flow.csv | Window-input counts, complete-case counts, unique people and outcome distributions |
| psm_effects.csv | Matched means, differences, SMDs, clustered inference and comparison counts |
| psm_balance.csv | Covariate balance for the full matched sets |
| psm_outcome_balance.csv | Covariate balance for outcome-complete matched comparisons |
| psm_run_summary.csv | Propensity-score samples, common support, calipers and matched counts |
| matching_sample_sizes.csv | Analysis-specific matching samples |
| main_table3_spearman.csv | Correlations, p-values and pairwise observation counts for Main Table 3 |
| table_s3_t2_descriptive_statistics.csv and table_s3_t3_descriptive_statistics.csv | Descriptive statistics on the post-graduation regression samples |
| table_s4_group_sizes.csv | Overall-career trajectory-group counts and proportions |
| table_s4_group_descriptive_statistics.csv | Group summaries and variable-availability counts |
| group_distribution_summary.csv | Figure 2 group profiles |
| figure2_panel_a_standardized_means.csv | Figure 2 standardized means and intervals |
| kde_density_curves.csv | Figure 2 density curves and group medians |
| figure_estimates.csv | Displayed estimates, confidence intervals, units and raw coefficients for Figures 3–4 |
| software_versions.csv | Runtime and library versions |
| run_summary.json | Completed model and matching design counts |
| run_progress.log | Model estimation progress |

CSV files retain numerical precision. Display tables round coefficients and
standard errors to three decimals and show p-values below .001 as <0.001.
LPM display effects are percentage-point changes for a 0.1-unit increase.
PPML display effects are 100 × [exp(0.1 × coefficient) − 1].

Matching estimates are adjusted observational comparisons. Their confidence
intervals and p-values are clustered by mentee. Balance in the outcome-complete
sample is reported separately because individual focal measures may be missing.

# Data dictionary

All files in this directory are non-identifying aggregate data or saved model
outputs. No file contains PairID, MenteeID, MentorID, ORCID, or OpenAlex author
identifiers.

## Main and supplementary tables

- `main_table3_spearman.csv`: displayed Spearman correlations for 5-, 10-,
  and 20-year outcomes.
- `main_table3_spearman_audit.csv`: sample size, rho, and p-value behind each
  displayed correlation.
- `main_table3_network_policy_audit.csv`: use of the final all-paper mentorship
  network-size definition in Table 3.
- `table_s1_sample_construction.csv`: sample-construction flow.
- `table_s2_panel_a_thresholds.csv`: citation-elite journal thresholds.
- `table_s2_panel_b_classification.csv`: journal-classification summary.
- `table_s3_t1_descriptive_statistics.csv`: descriptive statistics under the
  1-year publication-lag definition.
- `table_s3_t2_descriptive_statistics.csv`: descriptive statistics under the
  2-year publication-lag definition.
- `table_s3_t3_descriptive_statistics.csv`: descriptive statistics under the
  3-year publication-lag definition.
- `table_s4_group_descriptive_statistics.csv`: group-level descriptive
  statistics across publication-lag definitions.

## Descriptive figure data

- `group_distribution_summary.csv`: group-specific quantiles, means, and
  standard deviations for the four mentorship-resource measures.
- `kde_density_curves.csv`: precomputed density-curve coordinates and medians
  for the public descriptive figure.

## Saved statistical outputs

- `network_size_rebuild_audit.csv`: non-identifying coverage and distribution
  audit for the final all-paper mentorship network-size control.
- `psm_run_summary.csv`: matching sample sizes, selected calipers, maximum
  post-matching SMD, and balance status.
- `psm_balance.csv`: covariate balance before and after matching.
- `psm_effects.csv`: matched means, mean differences, outcome SMDs, standard
  errors, and p-values.
- `regression_coefficients.csv`: coefficients, standard errors, confidence
  intervals, p-values, and sample sizes for the released regression models.
- `regression_diagnostics.csv`: convergence, AIC, dispersion, and sample-size
  diagnostics.
- `sample_flow.csv`: analysis-specific sample flow and zero-outcome summaries.
- `vif_diagnostics.csv`: variance-inflation-factor diagnostics.

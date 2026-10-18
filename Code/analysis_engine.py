"""Regression, propensity-score estimation and covariate matching."""
from __future__ import annotations
import argparse
import math
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import norm, ttest_ind, ttest_rel
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
CORE_TERMS = ['topic_continuity', 'network_consistency', 'direct_percent', 'log_PeerCount']
CONTROL_TERMS = ['h_index', 'AvgTopPubPerYear_Mentored', 'AvgPaperPerYear_Mentored', 'NetworkSize_Mentored']
REGRESSION_TERMS = CORE_TERMS + CONTROL_TERMS
PSM01_COVARIATES = ['log_h_index', 'log_AvgTopPubPerYear_Mentored', 'log_AvgPaperPerYear_Mentored', 'log_NetworkSize_Mentored']
PSM0_COVARIATES = ['log_h_index', 'log_NetworkSize_Mentored']
PSM0_OUTCOMES = ['direct_percent', 'log_PeerCount']
PSM1_OUTCOMES = CORE_TERMS
CALIPER_GRID = (0.2, 0.15, 0.1, 0.075, 0.05, 0.025)

def add_log_covariates(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    mapping = {'h_index': 'log_h_index', 'NetworkSize_Mentored': 'log_NetworkSize_Mentored', 'AvgTopPubPerYear_Mentored': 'log_AvgTopPubPerYear_Mentored', 'AvgPaperPerYear_Mentored': 'log_AvgPaperPerYear_Mentored'}
    for raw, logged in mapping.items():
        data[logged] = np.log1p(pd.to_numeric(data[raw], errors='coerce').clip(lower=0))
    if 'log_PeerCount' not in data:
        data['log_PeerCount'] = np.log1p(pd.to_numeric(data['PeerCount'], errors='coerce').clip(lower=0))
    return data

def dataset_label(family: str, gap: int, horizon: str) -> str:
    return f'{family}__t{gap}__{horizon}'

def model_formula(outcome: str) -> str:
    predictors = ' + '.join(REGRESSION_TERMS)
    return f'{outcome} ~ {predictors} + C(EffectiveGraduationYear)'

def complete_regression_sample(data: pd.DataFrame, outcomes: Iterable[str]) -> pd.DataFrame:
    needed = list(REGRESSION_TERMS) + ['PairID', 'MenteeID', 'MentorID', 'EffectiveGraduationYear', *outcomes]
    sample = data[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    sample['MenteeID'] = sample['MenteeID'].astype(str)
    sample['MentorID'] = sample['MentorID'].astype(str)
    return sample

def coefficient_rows(result: object, model_name: str, metadata: dict[str, object], terms: list[str]=REGRESSION_TERMS) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    params = result.params
    for term in terms:
        if term not in params.index:
            continue
        coefficient = float(params[term])
        rows.append({**metadata, 'model': model_name, 'term': term, 'coefficient': coefficient, 'std_error': float(result.bse[term]), 'statistic': float(result.tvalues[term]), 'p_value': float(result.pvalues[term]), 'ci_low': float(result.conf_int().loc[term, 0]), 'ci_high': float(result.conf_int().loc[term, 1]), 'exp_coefficient': float(np.exp(np.clip(coefficient, -700, 700))) if model_name.startswith(('PPML',)) else np.nan, 'nobs': int(result.nobs)})
    return rows

def two_way_ols_rows(result: object, sample: pd.DataFrame, metadata: dict[str, object]) -> list[dict[str, object]]:
    mentee_groups = pd.factorize(sample['MenteeID'].astype(str))[0]
    mentor_groups = pd.factorize(sample['MentorID'].astype(str))[0]
    covariance, _cov_mentee, _cov_mentor = cov_cluster_2groups(result, mentee_groups, mentor_groups)
    diagonal = np.diag(covariance)
    bse = np.sqrt(np.where(diagonal >= 0, diagonal, np.nan))
    names = list(result.params.index)
    rows: list[dict[str, object]] = []
    for term in REGRESSION_TERMS:
        if term not in names:
            continue
        position = names.index(term)
        coefficient = float(result.params.iloc[position])
        standard_error = float(bse[position])
        statistic = coefficient / standard_error if standard_error > 0 else np.nan
        p_value = 2 * norm.sf(abs(statistic)) if np.isfinite(statistic) else np.nan
        rows.append({**metadata, 'model': 'OLS-two-way-cluster', 'term': term, 'coefficient': coefficient, 'std_error': standard_error, 'statistic': statistic, 'p_value': p_value, 'ci_low': coefficient - 1.96 * standard_error, 'ci_high': coefficient + 1.96 * standard_error, 'exp_coefficient': np.nan, 'nobs': int(result.nobs)})
    return rows

def run_regressions(datasets: list[dict[str, object]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    coefficients: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    vif_rows: list[dict[str, object]] = []
    flow_rows: list[dict[str, object]] = []
    for item in datasets:
        family = str(item['family'])
        gap = int(item['gap'])
        horizon = str(item['horizon'])
        data = item['data']
        count_outcome = str(item['count_outcome'])
        rate_outcome = str(item['rate_outcome'])
        exposure_col = str(item['exposure'])
        label = dataset_label(family, gap, horizon)
        print(f'[REG] {label}', flush=True)
        data = data.copy()
        data['_exposure'] = pd.to_numeric(data[exposure_col], errors='coerce')
        raw_count = pd.to_numeric(data[count_outcome], errors='coerce')
        sample = complete_regression_sample(data, [count_outcome, rate_outcome, '_exposure'])
        sample = sample[sample['_exposure'].gt(0)].copy()
        metadata = {'family': family, 'gap': gap, 'horizon': horizon}
        flow_rows.append({**metadata, 'raw_rows': len(data), 'complete_regression_rows': len(sample), 'complete_case_retention': len(sample) / len(data), 'unique_mentees': sample['MenteeID'].nunique(), 'unique_mentors': sample['MentorID'].nunique(), 'raw_zero_count_rows': int(raw_count.eq(0).sum()), 'raw_zero_count_share': float(raw_count.eq(0).mean()), 'raw_count_mean': float(raw_count.mean()), 'zero_count_rows': int(sample[count_outcome].eq(0).sum()), 'zero_count_share': float(sample[count_outcome].eq(0).mean()), 'count_mean': float(sample[count_outcome].mean()), 'count_variance': float(sample[count_outcome].var()), 'rate_skewness': float(sample[rate_outcome].skew())})
        formula_rate = model_formula(rate_outcome)
        ols_plain = smf.ols(formula_rate, data=sample).fit()
        ols_cluster = smf.ols(formula_rate, data=sample).fit(cov_type='cluster', cov_kwds={'groups': sample['MenteeID']})
        coefficients.extend(coefficient_rows(ols_cluster, 'OLS-cluster-mentee', metadata))
        try:
            coefficients.extend(two_way_ols_rows(ols_plain, sample, metadata))
            two_way_status = 'ok'
        except Exception as exc:
            two_way_status = f'failed: {type(exc).__name__}: {exc}'
        ppml = smf.glm(model_formula(count_outcome), data=sample, family=sm.families.Poisson(), offset=np.log(sample['_exposure'])).fit(maxiter=200, cov_type='cluster', cov_kwds={'groups': sample['MenteeID']})
        coefficients.extend(coefficient_rows(ppml, 'PPML-cluster-mentee', metadata))
        any_name = '_any_top'
        sample[any_name] = sample[count_outcome].gt(0).astype(int)
        lpm = smf.ols(model_formula(any_name), data=sample).fit(cov_type='cluster', cov_kwds={'groups': sample['MenteeID']})
        coefficients.extend(coefficient_rows(lpm, 'LPM-any-cluster-mentee', metadata))
        diagnostics.extend([
            {**metadata, 'model': 'OLS', 'nobs': int(ols_plain.nobs), 'aic': float(ols_plain.aic),
             'dispersion': np.nan, 'converged': True, 'status': two_way_status},
            {**metadata, 'model': 'PPML', 'nobs': int(ppml.nobs), 'aic': float(ppml.aic),
             'dispersion': float(ppml.pearson_chi2 / ppml.df_resid),
             'converged': bool(ppml.converged), 'status': 'ok'},
            {**metadata, 'model': 'LPM', 'nobs': int(lpm.nobs), 'aic': float(lpm.aic),
             'dispersion': np.nan, 'converged': True, 'status': 'ok'}])
        vif_data = sample[REGRESSION_TERMS].astype(float)
        design = sm.add_constant(vif_data, has_constant='add')
        for position, variable in enumerate(design.columns):
            if variable == 'const':
                continue
            vif_rows.append({**metadata, 'variable': variable, 'vif': float(variance_inflation_factor(design.values, position)), 'nobs': len(design)})
    return (pd.DataFrame(coefficients), pd.DataFrame(diagnostics), pd.DataFrame(vif_rows), pd.DataFrame(flow_rows))

def compute_smd(data: pd.DataFrame, treatment: str, variables: list[str]) -> dict[str, float]:
    treated = data.loc[data[treatment].eq(1)]
    control = data.loc[data[treatment].eq(0)]
    result: dict[str, float] = {}
    for variable in variables:
        pooled = np.sqrt((treated[variable].var() + control[variable].var()) / 2)
        difference = float(treated[variable].mean() - control[variable].mean())
        if not np.isfinite(pooled):
            raise ValueError(f'SMD requires at least two observed values per group: {variable}')
        if pooled == 0:
            result[variable] = 0.0 if difference == 0 else float(np.copysign(np.inf, difference))
        else:
            result[variable] = difference / pooled
    return result

def estimate_propensity(data: pd.DataFrame, treatment: str, covariates: list[str], random_state: int) -> pd.DataFrame:
    needed = [treatment, 'MenteeID', 'PairID', *covariates]
    model_data = data[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if model_data[treatment].nunique() != 2:
        raise ValueError(f'{treatment} does not have two groups')
    features = model_data[covariates].copy()
    for variable in covariates:
        features[f'{variable}__sq'] = features[variable] ** 2
    model = Pipeline([('scale', StandardScaler()), ('logit', LogisticRegression(max_iter=5000, solver='lbfgs', random_state=random_state))])
    model.fit(features, model_data[treatment].astype(int))
    score = np.clip(model.predict_proba(features)[:, 1], 1e-06, 1 - 1e-06)
    scored = data.loc[model_data.index].copy()
    scored['pscore'] = score
    scored['logit_pscore'] = np.log(score / (1 - score))
    treated = scored[scored[treatment].eq(1)]
    control = scored[scored[treatment].eq(0)]
    lower = max(treated['pscore'].min(), control['pscore'].min())
    upper = min(treated['pscore'].max(), control['pscore'].max())
    return scored[scored['pscore'].between(lower, upper)].copy()

def constrained_covariate_match(supported: pd.DataFrame, treatment: str, covariates: list[str], caliper_scale: float) -> tuple[pd.DataFrame, float]:
    treated = supported[supported[treatment].eq(1)].copy()
    control = supported[supported[treatment].eq(0)].copy()
    caliper = float(caliper_scale * supported['logit_pscore'].std())
    if not np.isfinite(caliper) or caliper <= 0 or treated.empty or control.empty:
        raise ValueError('Invalid caliper or empty treatment group')
    scaler = StandardScaler()
    scaled = scaler.fit_transform(supported[covariates])
    scaled = pd.DataFrame(scaled, index=supported.index, columns=covariates)
    control_x = scaled.loc[control.index, covariates].to_numpy()
    treated_x = scaled.loc[treated.index, covariates].to_numpy()
    tree = cKDTree(control_x)
    control_logit = control['logit_pscore'].to_numpy()
    treated_logit = treated['logit_pscore'].to_numpy()
    control_mentee = control['MenteeID'].astype(str).to_numpy()
    treated_mentee = treated['MenteeID'].astype(str).to_numpy()
    selected = np.full(len(treated), -1, dtype=int)
    remaining = np.arange(len(treated))
    k = min(32, len(control))
    while len(remaining) and k > 0:
        _distance, positions = tree.query(treated_x[remaining], k=k)
        positions = np.asarray(positions)
        if positions.ndim == 1:
            if len(remaining) == 1:
                positions = positions[None, :]
            else:
                positions = positions[:, None]
        still_missing: list[int] = []
        for local_position, treated_position in enumerate(remaining):
            candidates = np.atleast_1d(positions[local_position]).astype(int)
            valid = (np.abs(control_logit[candidates] - treated_logit[treated_position]) <= caliper) & (control_mentee[candidates] != treated_mentee[treated_position])
            valid_positions = np.flatnonzero(valid)
            if len(valid_positions):
                selected[treated_position] = candidates[valid_positions[0]]
            else:
                still_missing.append(treated_position)
        if not still_missing or k >= len(control):
            break
        remaining = np.asarray(still_missing, dtype=int)
        k = min(k * 2, len(control))
    keep = selected >= 0
    matched_treated = treated.iloc[np.flatnonzero(keep)].copy()
    matched_control = control.iloc[selected[keep]].copy()
    pair_numbers = np.arange(len(matched_treated))
    matched_treated['match_pair'] = pair_numbers
    matched_control['match_pair'] = pair_numbers
    matched = pd.concat([matched_treated, matched_control], ignore_index=True)
    if matched.empty:
        raise ValueError('No treated observations could be matched within the caliper')
    if (matched.groupby('match_pair')['MenteeID'].nunique() != 2).any():
        raise RuntimeError('Same-mentee PairIDs were matched')
    return (matched, caliper)

def balance_table(before: pd.DataFrame, after: pd.DataFrame, treatment: str, covariates: list[str]) -> pd.DataFrame:
    smd_before = compute_smd(before, treatment, covariates)
    smd_after = compute_smd(after, treatment, covariates)
    rows = []
    for variable in covariates:
        tb = before.loc[before[treatment].eq(1), variable].dropna()
        cb = before.loc[before[treatment].eq(0), variable].dropna()
        ta = after.loc[after[treatment].eq(1), variable].dropna()
        ca = after.loc[after[treatment].eq(0), variable].dropna()
        rows.append({'covariate': variable, 'smd_before': smd_before[variable], 'smd_after': smd_after[variable], 'abs_smd_after': abs(smd_after[variable]), 'welch_p_before': float(ttest_ind(tb, cb, equal_var=False).pvalue), 'welch_p_after': float(ttest_ind(ta, ca, equal_var=False).pvalue)})
    return pd.DataFrame(rows)

def auto_match(supported: pd.DataFrame, treatment: str, covariates: list[str]) -> dict[str, object]:
    best: dict[str, object] | None = None
    for scale in CALIPER_GRID:
        matched, caliper = constrained_covariate_match(supported, treatment, covariates, scale)
        balance = balance_table(supported, matched, treatment, covariates)
        max_smd = float(balance['abs_smd_after'].max())
        candidate = {'matched': matched, 'balance': balance, 'max_smd': max_smd, 'caliper_scale': scale, 'caliper': caliper, 'matched_pairs': int(matched['match_pair'].nunique())}
        if best is None or max_smd < float(best['max_smd']) or (np.isclose(max_smd, float(best['max_smd'])) and int(candidate['matched_pairs']) > int(best['matched_pairs'])):
            best = candidate
        if max_smd <= 0.1:
            return candidate
    if best is None:
        raise RuntimeError('No valid match')
    return best


TRAINING_TERMS = ['direct_percent', 'log_PeerCount', 'log_h_index',
                  'log_NetworkSize_Mentored', 'log_AvgPaperPerYear_Mentored']


def run_training_lpm(item):
    data = item['data'].copy()
    count = pd.to_numeric(data.TopPub_Mentored, errors='coerce')
    data['_training_positive'] = count.gt(0).where(count.notna())
    needed = ['PairID', 'MenteeID', 'EffectiveGraduationYear', '_training_positive', *TRAINING_TERMS]
    sample = data[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    sample['_training_positive'] = sample['_training_positive'].astype(int)
    sample['MenteeID'] = sample.MenteeID.astype(str)
    formula = '_training_positive ~ ' + ' + '.join(TRAINING_TERMS) + ' + C(EffectiveGraduationYear)'
    fit = smf.ols(formula, data=sample).fit(cov_type='cluster', cov_kwds={'groups': sample.MenteeID})
    meta = dict(family='mentorship_period', gap=int(item['gap']), horizon='pre_graduation')
    coefficients = pd.DataFrame(coefficient_rows(fit, 'LPM-mentorship-cluster-mentee', meta, TRAINING_TERMS))
    design = sm.add_constant(sample[TRAINING_TERMS].astype(float), has_constant='add')
    vif = pd.DataFrame([{**meta, 'variable': name,
                         'vif': float(variance_inflation_factor(design.to_numpy(), j)), 'nobs': len(sample)}
                        for j, name in enumerate(design.columns) if name != 'const'])
    diagnostics = pd.DataFrame([{**meta, 'model': 'LPM', 'nobs': len(sample), 'aic': float(fit.aic),
                                 'dispersion': np.nan, 'converged': True, 'status': 'ok'}])
    flow = pd.DataFrame([{**meta, 'raw_rows': len(data), 'complete_regression_rows': len(sample),
                          'complete_case_retention': len(sample) / len(data),
                          'unique_mentees': sample.MenteeID.nunique(),
                          'positive_outcome_rows': int(sample._training_positive.sum())}])
    return coefficients, diagnostics, vif, flow

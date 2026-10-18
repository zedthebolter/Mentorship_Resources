"""Estimate regression and matching models from pair-level indicators."""
from __future__ import annotations

import os
for _key in ['OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[_key] = '1'

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time

import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde, spearmanr
import statsmodels.formula.api as smf
from threadpoolctl import threadpool_limits

import analysis_engine as engine

GROUPS = ['G1a', 'G1b', 'G2a', 'G2b']
DESCRIPTIVE = engine.REGRESSION_TERMS + ['AvgTopPubPerYear_Post', 'PeerCount', 'PostCareerYears']


def load_item(root, item):
    item = dict(item)
    data = pd.read_csv(Path(root) / item['file'], float_precision='round_trip')
    if item['family'] == 'landmark':
        data.loc[data.PaperCount_Capability.eq(0), 'network_consistency'] = np.nan
    item['data'] = engine.add_log_covariates(data)
    return item


def regression_sample(item):
    d = item['data'].copy()
    d['_exposure'] = pd.to_numeric(d[item['exposure']], errors='coerce')
    c = engine.complete_regression_sample(d, [item['count_outcome'], item['rate_outcome'], '_exposure'])
    return c[c._exposure.gt(0)].copy()


def matched_effect(matched, supported, treatment, outcome, covariates):
    treated = matched.loc[matched[treatment].eq(1), ['match_pair', outcome]].set_index('match_pair')[outcome]
    control = matched.loc[matched[treatment].eq(0), ['match_pair', outcome]].set_index('match_pair')[outcome]
    pairs = pd.concat([treated.rename('treated'), control.rename('control')], axis=1)
    pairs = pairs.replace([np.inf, -np.inf], np.nan).dropna()
    complete = matched[matched.match_pair.isin(pairs.index)].copy()
    assert len(complete) == 2 * len(pairs)
    assert (complete.groupby('match_pair')[treatment].sum() == 1).all()
    if len(pairs) < 2 or complete.MenteeID.nunique() < 2:
        raise ValueError(f'Insufficient complete matched comparisons for {outcome}')
    clustered = smf.ols(f'{outcome} ~ {treatment}', data=complete).fit(
        cov_type='cluster', cov_kwds={'groups': complete.MenteeID.astype(str)})
    difference = float((pairs.treated - pairs.control).mean())
    assert np.isclose(clustered.params[treatment], difference, rtol=1e-9, atol=1e-11)
    balance = engine.balance_table(supported, complete, treatment, covariates)
    max_smd = float(balance.abs_smd_after.max())
    effect = dict(outcome=outcome, matched_pairs_with_outcome=len(pairs),
                  actual_test_n=int(clustered.nobs), unique_mentees=complete.MenteeID.nunique(),
                  unique_pair_records=complete.PairID.nunique(),
                  treated_mean=float(pairs.treated.mean()), control_mean=float(pairs.control.mean()),
                  mean_difference=difference, clustered_coefficient=float(clustered.params[treatment]),
                  outcome_smd=engine.compute_smd(complete, treatment, [outcome])[outcome],
                  clustered_std_error=float(clustered.bse[treatment]),
                  clustered_p_value=float(clustered.pvalues[treatment]),
                  outcome_max_abs_covariate_smd=max_smd, outcome_balance_pass=max_smd <= .10)
    return effect, balance


def run_job(root, item, kind):
    started = time.time()
    with threadpool_limits(limits=1):
        loaded = load_item(root, item)
        meta = {k: loaded[k] for k in ['family', 'gap', 'horizon']}
        if kind == 'regression':
            coefficient, diagnostics, vif, flow = engine.run_regressions([loaded])
            return dict(kind=kind, metadata=meta, seconds=time.time()-started,
                        coefficient=coefficient, diagnostics=diagnostics, vif=vif, flow=flow)
        if kind == 'training_lpm':
            coefficient, diagnostics, vif, flow = engine.run_training_lpm(loaded)
            return dict(kind=kind, metadata=meta, seconds=time.time()-started,
                        coefficient=coefficient, diagnostics=diagnostics, vif=vif, flow=flow)
        data = loaded['data'].copy()
        input_rows = len(data)
        if kind == 'PSM0':
            meta.update(family='mentorship_period', horizon='pre_graduation')
            treatment, covariates, outcomes = 'T0', engine.PSM0_COVARIATES, engine.PSM0_OUTCOMES
            data[treatment] = data.TopPub_Mentored.gt(0).astype(int)
            cutoff = None
        elif kind == 'PSM1':
            treatment, covariates = 'T1', engine.PSM01_COVARIATES
            outcomes = engine.CORE_TERMS[:2] if loaded['family'] == 'landmark' else engine.PSM1_OUTCOMES
            data[treatment] = data[loaded['count_outcome']].gt(0).astype(int)
            cutoff = None
        else:
            variable = kind.split(':', 1)[1]
            data = data[data[loaded['count_outcome']].gt(0)].dropna(subset=[variable]).copy()
            cutoff = float(data[variable].median())
            treatment, covariates, outcomes = 'T2', engine.PSM01_COVARIATES, [loaded['rate_outcome']]
            data[treatment] = data[variable].gt(cutoff).astype(int)
        needed = [treatment, 'MenteeID', 'PairID', *covariates]
        fit_rows = len(data[needed].replace([np.inf, -np.inf], np.nan).dropna())
        supported = engine.estimate_propensity(data, treatment, covariates, 42)
        result = engine.auto_match(supported, treatment, covariates)
        matched = result['matched']
        common = dict(**meta, analysis=kind, treatment=treatment, treatment_cutoff=cutoff,
                      input_rows=input_rows, design_eligible_rows=len(data), propensity_fit_rows=fit_rows,
                      common_support_rows=len(supported), ps_model_rows=len(supported),
                      treated_supported=int(supported[treatment].sum()),
                      control_supported=int(len(supported)-supported[treatment].sum()),
                      matched_pairs=int(result['matched_pairs']), caliper_scale=float(result['caliper_scale']),
                      caliper_logit_ps=float(result['caliper']), max_abs_smd_after=float(result['max_smd']),
                      balance_pass=float(result['max_smd']) <= .10)
        effects, outcome_balance = [], []
        for outcome in outcomes:
            eff, bal = matched_effect(matched, supported, treatment, outcome, covariates)
            effects.append({**common, **eff})
            outcome_balance.extend([{**meta, 'analysis': kind, 'outcome': outcome, **r}
                                    for r in bal.to_dict('records')])
        initial_balance = [{**common, **r} for r in result['balance'].to_dict('records')]
        return dict(kind=kind, metadata=meta, seconds=time.time()-started,
                    effects=pd.DataFrame(effects), outcome_balance=pd.DataFrame(outcome_balance),
                    initial_balance=pd.DataFrame(initial_balance), psm_summary=pd.DataFrame([common]))


def add_group(data):
    rates = data[['AvgTopPubPerYear_Mentored', 'AvgTopPubPerYear_Post']].replace([np.inf, -np.inf], np.nan)
    valid = rates.notna().all(axis=1)
    result = data.loc[valid].copy()
    m, n = result.AvgTopPubPerYear_Mentored, result.AvgTopPubPerYear_Post
    result['Group'] = np.select([m.gt(0) & n.gt(m), m.eq(0) & n.gt(0), m.gt(0) & n.le(m)],
                                ['G1a', 'G1b', 'G2a'], default='G2b')
    assert ((m >= 0) & (n >= 0)).all()
    return result


def write_descriptives(root, manifest):
    output = root / 'Results'
    s3, s4, groups, corr = [], [], [], []
    overall_t3 = None
    for record in manifest.to_dict('records'):
        item = load_item(root, record)
        d, c = item['data'], regression_sample(item)
        if item['family'] != 'landmark':
            for variable in engine.REGRESSION_TERMS + [item['rate_outcome']]:
                values = c[variable]
                s3.append(dict(Lag=item['gap'], Design=item['family'], Horizon=item['horizon'],
                               Variable=variable, N=len(c), Mean=values.mean(), Median=values.median(), SD=values.std(ddof=1)))
        if item['family'] == 'conventional' and item['gap'] == 3:
            for variable in engine.REGRESSION_TERMS:
                pair = d[[variable, item['rate_outcome']]].replace([np.inf, -np.inf], np.nan).dropna()
                rho, p = spearmanr(pair[variable], pair[item['rate_outcome']])
                corr.append(dict(window=int(item['horizon'][1:]), variable=variable, n=len(pair), spearman_rho=rho, p_value=p))
        if item['family'] != 'overall':
            continue
        classified = add_group(d)
        for group in GROUPS:
            sub = classified[classified.Group.eq(group)]
            groups.append(dict(Lag=item['gap'], Group=group, N=len(sub), classified_total=len(classified),
                               excluded_missing_rates=len(d)-len(classified), percent=100*len(sub)/len(classified)))
            for variable in DESCRIPTIVE:
                values = pd.to_numeric(sub[variable], errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
                s4.append(dict(Lag=item['gap'], Group=group, Variable=variable, Group_N=len(sub),
                               **{'Available N': len(values)}, Mean=values.mean(), Median=values.median(), SD=values.std(ddof=1)))
        if item['gap'] == 3:
            overall_t3 = classified
    s3 = pd.DataFrame(s3)
    for gap in (2, 3):
        s3[s3.Lag.eq(gap)].to_csv(output / f'table_s3_t{gap}_descriptive_statistics.csv', index=False)
    pd.DataFrame(s4).to_csv(output / 'table_s4_group_descriptive_statistics.csv', index=False)
    pd.DataFrame(groups).to_csv(output / 'table_s4_group_sizes.csv', index=False)
    pd.DataFrame(corr).to_csv(output / 'main_table3_spearman.csv', index=False)
    build_figure2_inputs(output, overall_t3)


def build_figure2_inputs(output, data):
    summary, density, bars = [], [], []
    variables = {'topic_continuity': 'Topic_Continuity', 'network_consistency': 'Net_Consistency',
                 'direct_percent': 'Direct_Percent', 'log_PeerCount': 'PeerCount_log'}
    for variable, label in variables.items():
        block = []
        for group in GROUPS:
            v = data.loc[data.Group.eq(group), variable].replace([np.inf, -np.inf], np.nan).dropna()
            row = dict(Variable=label, Source_column=variable, Group=group, N=len(v), Mean=v.mean(), Std=v.std(ddof=1),
                       P10=v.quantile(.1), Q1=v.quantile(.25), Median=v.median(), Q3=v.quantile(.75), P90=v.quantile(.9))
            summary.append(row); block.append(row)
        b = pd.DataFrame(block)
        center, scale = b.Mean.mean(), b.Mean.std(ddof=1)
        for row in block:
            z = (row['Mean']-center)/scale
            se = row['Std']/np.sqrt(row['N'])/scale
            bars.append(dict(variable=variable, group=row['Group'], n=row['N'], standardized_mean=z,
                             ci_low=z-1.96*se, ci_high=z+1.96*se))
    for panel, variable in [('network', 'NetworkSize_Mentored'), ('hindex', 'h_index')]:
        for group in GROUPS:
            v = np.log10(data.loc[data.Group.eq(group), variable].dropna()+1)
            grid = np.linspace(max(0, float(v.min())-.08*float(v.std())), float(v.max())+.08*float(v.std()), 240)
            kde = gaussian_kde(v.to_numpy(), bw_method='scott')
            density += [dict(Panel=panel, Group=group, Kind='curve', Order=i, X=x, Y=y)
                        for i, (x, y) in enumerate(zip(grid, kde(grid)))]
            density.append(dict(Panel=panel, Group=group, Kind='median', Order=0, X=v.median(), Y=np.nan))
    pd.DataFrame(summary).to_csv(output / 'group_distribution_summary.csv', index=False)
    pd.DataFrame(density).to_csv(output / 'kde_density_curves.csv', index=False)
    pd.DataFrame(bars).to_csv(output / 'figure2_panel_a_standardized_means.csv', index=False)




def run_all(root, workers=2):
    root = Path(root).resolve()
    output = root / 'Results'
    output.mkdir(exist_ok=True)
    manifest = pd.read_csv(root / 'Data/dataset_manifest.csv')
    if len(manifest) != 12 or set(manifest.gap) != {2, 3}:
        raise ValueError('The input manifest must contain six designs for each of t2 and t3')
    for row in manifest.to_dict('records'):
        if hashlib.sha256((root / row['file']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Input checksum does not match the dataset manifest')
    jobs = [(r, 'regression') for r in manifest.to_dict('records')]
    overall = manifest[manifest.family.eq('overall')].to_dict('records')
    jobs += [(r, 'training_lpm') for r in overall]
    jobs += [(r, 'PSM0') for r in overall]
    for row in manifest.to_dict('records'):
        variables = engine.CORE_TERMS[:2] if row['family'] == 'landmark' else engine.CORE_TERMS
        jobs += [(row, 'PSM1')] + [(row, 'PSM2:' + v) for v in variables]
    started = time.time()
    buckets = {key: [] for key in ['coefficient', 'diagnostics', 'vif', 'flow', 'effects',
                                    'outcome_balance', 'initial_balance', 'psm_summary']}
    print(f'Estimating {len(jobs)} jobs from {len(manifest)} input tables; workers={workers}', flush=True)
    with (output / 'run_progress.log').open('w', encoding='utf-8') as log:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            pending = [pool.submit(run_job, str(root), row, kind) for row, kind in jobs]
            for i, future in enumerate(as_completed(pending), 1):
                result = future.result()
                meta = result['metadata']
                message = f"{i}/{len(jobs)} {result['kind']} {meta['family']} t{meta['gap']} {meta['horizon']} ({result['seconds']:.1f}s)"
                print(message, flush=True)
                log.write(message + '\n')
                log.flush()
                for key in buckets:
                    if key in result:
                        buckets[key].append(result[key])
    names = {'coefficient': 'regression_coefficients', 'diagnostics': 'regression_diagnostics',
             'vif': 'vif_diagnostics', 'flow': 'sample_flow', 'effects': 'psm_effects',
             'outcome_balance': 'psm_outcome_balance', 'initial_balance': 'psm_balance',
             'psm_summary': 'psm_run_summary'}
    for key, frames in buckets.items():
        columns = list(dict.fromkeys(column for frame in frames for column in frame.columns))
        observed_frames = [frame.dropna(axis=1, how='all') for frame in frames]
        combined = pd.concat(observed_frames, ignore_index=True).reindex(columns=columns)
        combined.sort_values(['family', 'gap', 'horizon']).to_csv(
            output / (names[key] + '.csv'), index=False)
    effects = pd.read_csv(output / 'psm_effects.csv')
    fields = ['family', 'gap', 'horizon', 'analysis', 'outcome', 'input_rows', 'design_eligible_rows',
              'propensity_fit_rows', 'common_support_rows', 'matched_pairs', 'matched_pairs_with_outcome',
              'actual_test_n', 'unique_mentees', 'unique_pair_records', 'outcome_balance_pass']
    effects[fields].to_csv(output / 'matching_sample_sizes.csv', index=False)
    write_descriptives(root, manifest)
    from export_tables import build
    build(root)
    from make_figures import make_figures
    make_figures(root)
    versions = [dict(package='Python', version=platform.python_version())]
    for package in ['numpy', 'pandas', 'scipy', 'statsmodels', 'scikit-learn', 'matplotlib', 'nbformat', 'nbclient']:
        versions.append(dict(package=package, version=importlib.metadata.version(package)))
    pd.DataFrame(versions).to_csv(output / 'software_versions.csv', index=False)
    reg = pd.read_csv(output / 'regression_coefficients.csv')
    summary = dict(post_graduation_regression_designs=len(manifest), mentorship_lpm_designs=len(overall),
                   matching_designs=sum(kind.startswith('PSM') for _, kind in jobs),
                   regression_coefficient_rows=len(reg), matching_outcome_rows=len(effects),
                   matching_balance_failures=int((~effects.outcome_balance_pass).sum()),
                   elapsed_seconds=round(time.time() - started, 1))
    if summary['matching_balance_failures']:
        raise RuntimeError('A released matching comparison exceeds the balance threshold')
    (output / 'run_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('Completed:', summary, flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    run_all(args.root, args.workers)

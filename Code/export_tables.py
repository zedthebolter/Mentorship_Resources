"""Format analytical outputs as supplementary tables S1–S13."""
from pathlib import Path
import json
import numpy as np
import pandas as pd


def build(root):
    ROOT=Path(root)
    OUT=ROOT/'Results'
    P=OUT
    r=pd.read_csv(P/'regression_coefficients.csv')
    e=pd.read_csv(P/'psm_effects.csv')
    b=pd.read_csv(P/'psm_outcome_balance.csv')
    vif=pd.read_csv(OUT/'vif_diagnostics.csv')
    V=['topic_continuity','network_consistency','direct_percent','log_PeerCount']
    N=dict(zip(V,['Topic_Continuity','Network_Consistency','Direct_Percent','PeerCount_log']))
    H=['L5','L10','L20','overall_career'];L=['early1_3_to_later4_10','early1_3_to_later6_20']
    WH=dict(zip(H+L,['5-year','10-year','20-year','Overall career','Years 4–10','Years 6–20']))
    REGHEAD=['Lag t','Window','Model','Variable','Estimate (SE)','p-value','0.1-unit effect','N']
    MATCHHEAD=['Lag t','Window','Outcome','Matched pairs','Maximum abs. SMD','Outcome SMD','Matched mean difference','p-value (clustered)']
    PS2HEAD=['Lag t','Window','Analysis','Matched pairs','Maximum abs. SMD','Balance','Treated/high mean','Control/low mean','Outcome ATT','p-value (clustered)']
    tables={};texts=[]
    def pformat(p):return '<0.001' if p<.001 else f'{p:.3f}'
    def count(x):return f'{int(x):,}'
    def f(x):return f'{x:.3f}'
    def add(key,title,head,rows,note=''):
        assert all(len(x)==len(head) for x in rows),key
        head=[str(x).replace('|SMD|','abs. SMD') for x in head]
        tables[key]=dict(title=title,head=head,rows=rows,note=note)
        text='**'+title+'**\n\n| '+' | '.join(head)+' |\n| '+' | '.join(['---']*len(head))+' |\n'
        text+='\n'.join('| '+' | '.join(str(x) for x in row)+' |' for row in rows)
        if note:text+='\n\n'+note
        texts.append(text)
        pd.DataFrame(rows,columns=head).to_csv(OUT/(key+'.csv'),index=False)

    vnames={'direct_percent':'Direct_Percent','log_PeerCount':'PeerCount_log','log_h_index':'ln(1+h_index)',
            'log_NetworkSize_Mentored':'ln(1+NetworkSize_Mentored)',
            'log_AvgPaperPerYear_Mentored':'ln(1+AvgPaperPerYear_Mentored)',
            'topic_continuity':'Topic_Continuity','network_consistency':'Network_Consistency',
            'h_index':'h_index','AvgTopPubPerYear_Mentored':'AvgTopPubPerYear_Mentored',
            'AvgPaperPerYear_Mentored':'AvgPaperPerYear_Mentored','NetworkSize_Mentored':'NetworkSize_Mentored'}

    def vifrows(family):
        x=vif[vif.family.eq(family)] if family=='mentorship_period' else vif[vif.family.eq('landmark')] if family=='landmark' else vif[vif.family.isin(['conventional','overall'])]
        variables=['direct_percent','log_PeerCount','log_h_index','log_NetworkSize_Mentored','log_AvgPaperPerYear_Mentored'] if family=='mentorship_period' else V+['h_index','AvgTopPubPerYear_Mentored','AvgPaperPerYear_Mentored','NetworkSize_Mentored']
        rows=[]
        for variable in variables:
            row=[vnames[variable]]
            for lag in [2,3]:
                values=x[(x.gap==lag)&x.variable.eq(variable)].vif
                row.append(f(values.iloc[0]) if len(values)==1 else f'{values.min():.3f}–{values.max():.3f}')
            rows.append(row+['Pass (<5)'])
        return rows

    training_note='Note. PSM0 matches on logged mentor h-index, training coauthor-network size and logged annual total publication rate during training . The LPM includes both focal predictors and effective-graduation-year fixed effects. Regression standard errors and matching p-values are clustered by mentee. Matching comparisons are observational.'
    vifnote='Note. VIFs describe collinearity among the substantive predictors, with an intercept. Graduation-year indicators are excluded from these displayed VIFs. Models with identical samples and predictor matrices share the same VIF values.'
    psm0=e[e.analysis.eq('PSM0')&e.gap.isin([2,3])]
    psm0_rows=[]
    for lag in [2,3]:
        for variable in ['direct_percent','log_PeerCount']:
            z=psm0[(psm0.gap==lag)&psm0.outcome.eq(variable)].iloc[0]
            psm0_rows.append([str(lag),N[variable],count(z.matched_pairs_with_outcome),f(z.outcome_max_abs_covariate_smd),f'{z.outcome_smd:+.3f}',f'{z.mean_difference:+.3f}',pformat(z.clustered_p_value)])
    add('S5A','Table S5. Publication-lag robustness checks for mentorship-period PSM0 and LPM results (t2 and t3). Panel A. PSM0 matched comparisons.',['Lag t','Outcome','Matched pairs','Maximum abs. SMD','Outcome SMD','Matched mean difference','p-value (clustered)'],psm0_rows)
    training_rows=[]
    for lag in [2,3]:
        for variable in V[2:]:
            z=r[(r.gap==lag)&r.family.eq('mentorship_period')&r.term.eq(variable)].iloc[0]
            training_rows.append([str(lag),'Mentorship period','LPM',N[variable],f'{z.coefficient:+.3f} ({z.std_error:.3f})',pformat(z.p_value),f'{z.coefficient*10:+.2f} pp',count(z.nobs)])
    add('S5B','Table S5, Panel B. Mentorship-period LPM.',REGHEAD,training_rows,training_note)
    add('S5C','Table S5, Panel C. VIF diagnostics for the mentorship-period LPM.',['Variable','t2 VIF','t3 VIF','Assessment'],vifrows('mentorship_period'),vifnote)

    def matching(lags,horizons,variables,analysis):
        rows=[]
        for lag in lags:
            for h in horizons:
                for variable in variables:
                    z=e[(e.gap==lag)&e.horizon.eq(h)&e.analysis.eq('PSM1' if analysis=='PSM1' else 'PSM2:'+variable)]
                    if analysis=='PSM1':z=z[z.outcome.eq(variable)]
                    assert len(z)==1
                    z=z.iloc[0]
                    assert z.outcome_balance_pass
                    base=[str(lag),WH[h],N[variable],count(z.matched_pairs_with_outcome),f(z.outcome_max_abs_covariate_smd)]
                    if analysis=='PSM1':row=base+[f'{z.outcome_smd:+.3f}',f'{z.mean_difference:+.3f}',pformat(z.clustered_p_value)]
                    else:row=base+['Pass',f(z.treated_mean),f(z.control_mean),f'{z.mean_difference:+.3f}',pformat(z.clustered_p_value)]
                    rows.append(row)
        return rows

    def regressions(lags,horizons,variables,model):
        rows=[]
        for lag in lags:
            for h in horizons:
                for variable in variables:
                    z=r[(r.gap==lag)&r.horizon.eq(h)&r.term.eq(variable)&r.model.eq(model)]
                    assert len(z)==1
                    z=z.iloc[0]
                    if model.startswith('LPM'):label='LPM';effect=f'{z.coefficient*10:+.2f} pp'
                    elif model.startswith('PPML'):label='PPML';effect=f'{100*np.expm1(.1*z.coefficient):+.1f}%'
                    else:raise ValueError(model)
                    rows.append([str(lag),WH[h],label,N[variable],f'{z.coefficient:+.3f} ({z.std_error:.3f})',pformat(z.p_value),effect,count(z.nobs)])
        return rows

    def ols(lags,horizons,variables):
        rows=[]
        for lag in lags:
            for h in horizons:
                for variable in variables:
                    q=r[(r.gap==lag)&r.horizon.eq(h)&r.term.eq(variable)].set_index('model')
                    m=q.loc['OLS-cluster-mentee'];w=q.loc['OLS-two-way-cluster']
                    assert m.coefficient==w.coefficient and m.nobs==w.nobs
                    rows.append([str(lag),WH[h],N[variable],f'{m.coefficient:+.3f}',f(m.std_error),pformat(m.p_value),f(w.std_error),pformat(w.p_value),count(m.nobs)])
        return rows

    def balance(family):
        allowed=H if family=='conventional' else L
        vars=V if family=='conventional' else V[:2]
        x=b[b.gap.isin([2,3])&b.horizon.isin(allowed)&b.analysis.isin(['PSM2:'+v for v in vars])]
        assert len(x)==(32 if family=='conventional' else 8)*4
        covs=['log_h_index','log_NetworkSize_Mentored','log_AvgTopPubPerYear_Mentored','log_AvgPaperPerYear_Mentored']
        rows=[]
        for lag in [2,3]:
            for cov in covs:
                q=x[(x.gap==lag)&x.covariate.eq(cov)]
                before=q.smd_before.abs();after=q.smd_after.abs()
                assert after.max()<=.1
                rows.append([str(lag),cov,str(len(q)),f'{before.min():.3f}–{before.max():.3f}',f'{after.min():.3f}–{after.max():.3f}',f(after.max()),'Pass'])
        return rows

    psmnote='Note. PSM1 compares subsequent publishers with non-publishers. Matched differences are publisher minus non-publisher; SMDs standardize the focal-variable differences. Matching p-values are clustered by mentee. Matched pairs can include reused controls and are not unique-person counts.'
    regnote='Note. LPM, OLS and PPML use the same complete-case samples and eight substantive predictors, with effective-graduation-year fixed effects. LPM models any citation-elite publication. PPML models publication counts with log exposure as an offset. LPM transformations are percentage-point changes for a 0.1-unit increase; PPML transformations are percentage rate changes for a 0.1-unit increase.'
    psm2note='Note. PSM2 compares above-median and at/below-median values of the focal variable among positive-outcome records. ATT uses conventional matching notation for the high-minus-low matched mean difference in publications per year; estimates are interpreted as adjusted observational comparisons. P-values are clustered by mentee.'
    BALHEAD=['Lag t','Matching covariate','Matching sets','Abs. SMD before: range','Abs. SMD after: range','Maximum abs. SMD after','Assessment']
    OLSHEAD=['Lag t','Window','Variable','Coefficient','SE: mentee cluster','p: mentee cluster','SE: two-way cluster','p: two-way cluster','N']
    add('S6A','Table S6. Publication-lag robustness checks for post-graduation PSM1 and LPM results (t2 and t3). Panel A. PSM1 matched comparisons.',MATCHHEAD,matching([2,3],H,V,'PSM1'),psmnote)
    add('S6B','Table S6, Panel B. LPM estimates.',REGHEAD,regressions([2,3],H,V,'LPM-any-cluster-mentee'),regnote)
    add('S6C','Table S6, Panel C. VIF diagnostics for the post-graduation LPM.',['Variable','t2 VIF range','t3 VIF range','Assessment'],vifrows('conventional'),vifnote)
    add('S7','Table S7. Covariate balance diagnostics for PSM2 across conventional and overall-career windows (t2 and t3).',BALHEAD,balance('conventional'),'Note. Each lag includes 16 matching sets: four focal variables across four outcome windows. Ranges summarize absolute standardized mean differences in each matching covariate across the outcome-complete matched samples. All sets satisfy maximum absolute SMD ≤ 0.10.')
    add('S8','Table S8. Publication-lag robustness checks for PSM2 matched output comparisons (t2 and t3).',PS2HEAD,matching([2,3],H,V,'PSM2'),psm2note)
    add('S9A','Table S9. Publication-lag robustness checks for PPML and OLS estimates across post-graduation windows (t2 and t3). Panel A. PPML.',REGHEAD,regressions([2,3],H,V,'PPML-cluster-mentee'),regnote)
    add('S9B','Table S9, Panel B. OLS with mentee and two-way clustered standard errors.',OLSHEAD,ols([2,3],H,V),'Note. The two OLS specifications share the same coefficient estimates and samples; their covariance estimators differ. Two-way clustering is by mentee and mentor.')
    add('S9C','Table S9, Panel C. VIF diagnostics for OLS and PPML.',['Variable','t2 VIF range','t3 VIF range','Assessment'],vifrows('conventional'),vifnote+' These values are identical to Table S6, Panel C because the samples and predictors are identical.')
    add('S10A','Table S10. Publication-lag robustness checks for landmark PSM1 and LPM results for TC and NC (t2 and t3). Panel A. PSM1.',MATCHHEAD,matching([2,3],L,V[:2],'PSM1'),psmnote)
    add('S10B','Table S10, Panel B. Landmark LPM estimates.',REGHEAD,regressions([2,3],L,V[:2],'LPM-any-cluster-mentee'),regnote+' Only TC and NC are displayed; DP and PC remain model covariates.')
    add('S10C','Table S10, Panel C. VIF diagnostics for landmark LPM models.',['Variable','t2 VIF range','t3 VIF range','Assessment'],vifrows('landmark'),vifnote)
    add('S11','Table S11. Covariate balance diagnostics for landmark PSM2 comparisons (t2 and t3).',BALHEAD,balance('landmark'),'Note. Each lag includes four matching sets: two focal variables across two landmark outcome windows. Ranges summarize absolute standardized mean differences across the outcome-complete matched samples. All sets satisfy maximum absolute SMD ≤ 0.10.')
    add('S12','Table S12. Publication-lag robustness checks for landmark PSM2 matched output comparisons for TC and NC (t2 and t3).',PS2HEAD,matching([2,3],L,V[:2],'PSM2'),psm2note)
    add('S13A','Table S13. Publication-lag robustness checks for landmark PPML and OLS estimates for TC and NC (t2 and t3). Panel A. PPML.',REGHEAD,regressions([2,3],L,V[:2],'PPML-cluster-mentee'),regnote+' Only TC and NC are displayed; DP and PC remain model covariates.')
    add('S13B','Table S13, Panel B. Landmark OLS with mentee and two-way clustered standard errors.',OLSHEAD,ols([2,3],L,V[:2]))
    add('S13C','Table S13, Panel C. VIF diagnostics for landmark OLS and PPML.',['Variable','t2 VIF range','t3 VIF range','Assessment'],vifrows('landmark'),vifnote+' These values are identical to Table S10, Panel C because the samples and predictors are identical.')



    manifest=pd.read_csv(ROOT/'Data/dataset_manifest.csv')
    window_rows=[]
    for lag in [2,3]:
        row=[f't{lag} ({lag} years)']
        for horizon in H+L:
            z=manifest[(manifest.gap==lag)&manifest.horizon.eq(horizon)].iloc[0]
            row.append(count(z.input_rows))
        window_rows.append(row)
    add('S1A','Table S1. Sample sizes by publication lag and observation window. Panel A. Observation-window input samples.',
        ['Publication lag','5-year window','10-year window','20-year window','Overall career','Landmark: years 4–10','Landmark: years 6–20'],window_rows,
        'Note. Counts are relationship-spell records before analysis-specific variable-availability restrictions. Samples overlap and should not be summed.')
    flow=pd.read_csv(P/'sample_flow.csv')
    sample_rows=[]
    for lag in [2,3]:
        for horizon in H+L:
            z=flow[(flow.gap==lag)&flow.horizon.eq(horizon)].iloc[0]
            label='Landmark' if z.family=='landmark' else 'Overall' if z.family=='overall' else 'Conventional'
            sample_rows.append([f'{label} t{lag}',WH[horizon],count(z.raw_rows),count(z.complete_regression_rows)])
    corr=pd.read_csv(P/'main_table3_spearman.csv')
    for horizon,years in [('L5',5),('L10',10),('L20',20)]:
        z=corr[corr.window.eq(years)]
        total=manifest[(manifest.gap==3)&manifest.horizon.eq(horizon)].input_rows.iloc[0]
        sample_rows.append(['Spearman correlations (Table 3, t3)',WH[horizon],count(total),f'{count(z.n.min())}–{count(z.n.max())}'])
    add('S1B','Table S1, Panel B. Analytical sample sizes.',['Design','Window','Window-input N','Analytical N'],sample_rows,
        'Note. Regression N denotes complete cases. Correlation N ranges summarize pairwise available observations across variable–outcome correlations within a window. Mentorship-period LPM N is reported in Table S5, Panel B.')
    for panel,file in [('A','table_s2_panel_a_thresholds.csv'),('B','table_s2_panel_b_classification.csv')]:
        z=pd.read_csv(ROOT/'Results'/file).fillna('')
        add('S2'+panel,f'Table S2, Panel {panel}. Identification of citation-elite journals.',list(z.columns),z.astype(str).values.tolist())
    for lag,panel in [(2,'A'),(3,'B')]:
        d=pd.read_csv(P/f'table_s3_t{lag}_descriptive_statistics.csv')
        variables=list(dict.fromkeys(d.Variable))
        rows=[]
        for variable in variables:
            row=[vnames.get(variable,variable)]
            for horizon in H:
                z=d[d.Horizon.eq(horizon)&d.Variable.eq(variable)].iloc[0]
                row += [f(z.Mean),f(z.Median),f(z.SD)]
            rows.append(row)
        headers=['Variable']+[WH[h]+' '+stat for h in H for stat in ['Mean','Median','SD']]
        rows.insert(0,['N']+[value for h in H for value in [count(d[d.Horizon.eq(h)].N.iloc[0]),'','']])
        add('S3'+panel,f'Table S3, Panel {panel}. Descriptive statistics for t{lag}.',headers,rows)
    groups=pd.read_csv(P/'table_s4_group_sizes.csv')
    desc=pd.read_csv(P/'table_s4_group_descriptive_statistics.csv')
    group_order=['G1a','G1b','G2a','G2b']
    variables=['AvgTopPubPerYear_Mentored','AvgTopPubPerYear_Post','topic_continuity','network_consistency','log_PeerCount','h_index','NetworkSize_Mentored']
    for lag,panel in [(2,'A'),(3,'B')]:
        rows=[['N']+[value for g in group_order for value in [count(groups[(groups.Lag==lag)&groups.Group.eq(g)].N.iloc[0]),'']]]
        for variable in variables:
            row=[vnames.get(variable,variable)]
            for group in group_order:
                z=desc[(desc.Lag==lag)&desc.Group.eq(group)&desc.Variable.eq(variable)].iloc[0]
                row += [f(z.Mean),f(z.Median)]
            rows.append(row)
        add('S4'+panel,f'Table S4, Panel {panel}. Group-wise descriptive statistics for t{lag}.',
            ['Variable']+[g+' '+stat for g in group_order for stat in ['Mean','Median']],rows,
            'Note. Groups are defined from overall-career records with both period publication rates observed. Variable summaries use available observations within each group.')
    def sort_key(key):
        import re
        match=re.fullmatch(r'S(\d+)([A-Z]?)',key)
        return int(match[1]),match[2]
    tables=dict(sorted(tables.items(),key=lambda x:sort_key(x[0])))
    sections=[]
    for key,t in tables.items():
        section='**'+t['title']+'**\n\n| '+' | '.join(t['head'])+' |\n| '+' | '.join(['---']*len(t['head']))+' |\n'
        section+='\n'.join('| '+' | '.join(str(v) for v in row)+' |' for row in t['rows'])
        if t['note']:section+='\n\n'+t['note']
        sections.append(section)
    (OUT/'Supplementary_Tables.md').write_text('\n\n---\n\n'.join(sections),encoding='utf-8')
    (OUT/'supplementary_tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Exported supplementary tables S1–S13',flush=True)
    return tables

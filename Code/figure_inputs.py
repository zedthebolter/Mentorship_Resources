"""Collect clustered estimates and display transformations for Figures 3–4."""
from pathlib import Path
import numpy as np
import pandas as pd


def prepare_estimates(root):
    root=Path(root)
    reg=pd.read_csv(root/'Results/regression_coefficients.csv')
    psm=pd.read_csv(root/'Results/psm_effects.csv')
    psm0=psm[psm.analysis.eq('PSM0')]
    training=reg[reg.model.eq('LPM-mentorship-cluster-mentee')]
    WINDOWS=[('conventional','L5'),('conventional','L10'),('conventional','L20'),('overall','overall_career')]
    LANDMARK=[('landmark','early1_3_to_later4_10'),('landmark','early1_3_to_later6_20')]
    rows=[]

    def add(figure,panel,lag,family,horizon,method,variable,source):
        meta=dict(figure=figure,panel=panel,lag=lag,family=family,horizon=horizon,method=method,variable=variable)
        if method.startswith('PSM'):
            z=source.iloc[0]
            raw=float(z.mean_difference);se=float(z.clustered_std_error);p=float(z.clustered_p_value)
            low=raw-1.96*se;high=raw+1.96*se
            est=raw
            n=int(z.actual_test_n)
            assert z.outcome_balance_pass and z.outcome_max_abs_covariate_smd<=.10
            meta.update(matched_pairs=int(z.matched_pairs_with_outcome),unique_mentees=int(z.unique_mentees))
            units='matched mean difference' if method!='PSM2' else 'publications per year'
        else:
            z=source.iloc[0]
            raw=float(z.coefficient)
            se=float(z.std_error)
            p=float(z.p_value)
            n=int(z.nobs)
            if method=='LPM':
                est=raw*10;low=(raw-1.96*se)*10;high=(raw+1.96*se)*10
                units='percentage points per 0.1-unit increase'
            else:
                est=np.expm1(.1*raw)*100
                low=np.expm1(.1*(raw-1.96*se))*100
                high=np.expm1(.1*(raw+1.96*se))*100
                units='percent rate change per 0.1-unit increase'
        rows.append(dict(**meta,estimate=est,ci_low=low,ci_high=high,p_value=p,nobs=n,
                         raw_estimate=raw,raw_std_error=se,units=units))

    def pair_panel(figure,panel,lag,windows,variables,pair):
        for family,horizon in windows:
            for variable in variables:
                for method in pair:
                    if method.startswith('PSM'):
                        source=psm[(psm.gap==lag)&(psm.family==family)&(psm.horizon==horizon)]
                        if method=='PSM1':source=source[source.analysis.eq(method)&source.outcome.eq(variable)]
                        else:source=source[source.analysis.eq('PSM2:'+variable)]
                    else:
                        name='LPM-any-cluster-mentee' if method=='LPM' else 'PPML-cluster-mentee'
                        source=reg[(reg.gap==lag)&(reg.family==family)&(reg.horizon==horizon)&reg.term.eq(variable)&reg.model.eq(name)]
                    assert len(source)==1,(figure,panel,lag,family,horizon,method,variable,len(source))
                    add(figure,panel,lag,family,horizon,method,variable,source)

    for lag in [2,3]:
        for variable in ['direct_percent','log_PeerCount']:
            for method in ['PSM0','LPM']:
                source=psm0[(psm0.gap==lag)&psm0.outcome.eq(variable)] if method=='PSM0' else training[(training.gap==lag)&training.term.eq(variable)]
                assert len(source)==1
                add(3,'A',lag,'mentorship_period','pre_graduation',method,variable,source)
        pair_panel(3,'B',lag,WINDOWS,['direct_percent','log_PeerCount'],['PSM1','LPM'])
        pair_panel(3,'C',lag,WINDOWS,['direct_percent','log_PeerCount'],['PSM2','PPML'])
        pair_panel(4,'A',lag,WINDOWS,['topic_continuity','network_consistency'],['PSM1','LPM'])
        pair_panel(4,'B',lag,LANDMARK,['topic_continuity','network_consistency'],['PSM1','LPM'])
        pair_panel(4,'C',lag,WINDOWS,['topic_continuity','network_consistency'],['PSM2','PPML'])
        pair_panel(4,'D',lag,LANDMARK,['topic_continuity','network_consistency'],['PSM2','PPML'])
    d=pd.DataFrame(rows)
    assert len(d)==168
    assert not d.duplicated(['figure','panel','lag','horizon','method','variable']).any()
    assert np.isfinite(d[['estimate','ci_low','ci_high','p_value']]).all().all()
    assert d.ci_low.le(d.estimate).all() and d.ci_high.ge(d.estimate).all()
    d.to_csv(root/'Results/figure_estimates.csv',index=False)
    return d

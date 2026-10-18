# Analysis indicator tables

One row is one mentor–mentee relationship spell in one lag/design. Tables preserve
window/design input records before complete-case deletion. Blank numeric values
are missing. `dataset_manifest.csv` supplies each file's outcome and exposure fields,
row count and SHA-256 hash. gzip CSV is read directly with `pandas.read_csv`.

Complete-case regressions exclude relationship observations with no recorded
mentee publications during the extended mentorship period because the
collaboration measures are undefined.

| Column | Meaning |
|---|---|
| PairID | Anonymous relationship-spell ID, consistent across files |
| MenteeID | Anonymous mentee ID, required for grouping, matching exclusions and clustered errors |
| MentorID | Anonymous mentor ID, required for deduplication and two-way clustered sensitivity |
| EffectiveGraduationYear | Recorded mentorship end year plus publication lag; model fixed-effect year, not verified degree date |
| topic_continuity | Fraction of primary topics observed during the mentorship period that are retained in the subsequent measurement period; missing when the mentorship-period topic set is unavailable or empty |
| network_consistency | Fraction of the training mentor–mentee joint-publication coauthor network retained in the subsequent measurement period; zero is used for an observed empty initial network; required mapping and coverage failures remain missing |
| direct_percent | Fraction of mentorship-period mentee papers coauthored with the focal mentor; zero is retained |
| PeerCount | Number of other mentees sharing the mentor with overlapping extended mentorship intervals |
| log_PeerCount | Natural log of PeerCount+1 |
| h_index | Mentor h-index calculated from publications and citations accumulated before the recorded mentorship start year |
| AvgTopPubPerYear_Mentored | Annual citation-elite journal publication rate in extended mentorship period |
| AvgPaperPerYear_Mentored | Annual all-publication rate in extended mentorship period |
| NetworkSize_Mentored | Distinct coauthors across all mentorship-period papers, excluding the mentee |
| TopPub_Mentored | Citation-elite publication count during extended mentorship; PSM0 treatment equals 1 when this count is positive and 0 otherwise |
| TopPub_Post | Citation-elite publication count in the conventional or overall-career outcome period; PPML outcome, binary-outcome indicator and PSM1/PSM2 sample/group definition |
| AvgTopPubPerYear_Post | Annual rate in the conventional/overall outcome period |
| PostWindowYears | Fixed observation exposure for conventional windows |
| PostCareerYears | Last observed publication year minus effective boundary, truncated at zero; positive exposure required for regression |
| TopPub_Outcome | Citation-elite publication count in the later landmark outcome period; used in the same models and group definitions as TopPub_Post |
| AvgTopPubPerYear_Outcome | Annual citation-elite rate in the later landmark outcome period |
| OutcomeExposureYears | Landmark outcome-period exposure |
| PaperCount_Capability | All-publication count in landmark measurement years 1-3; an availability field, not a regression predictor. When zero, network_consistency is set to missing before analysis |

PSM0 compares any versus no citation-elite mentorship-period publication and matches
on log(h-index+1), log(network size+1) and logged annual total publication rate during
training. PSM1 compares any versus no outcome-period
citation-elite publication. PSM2 restricts to positive outcome-count records and
compares above-median versus at/below-median values of each focal variable.
PSM1/2 match on the four logged mentor/network/prior-publication covariates.
Full-match counts and outcome-complete comparison counts are distinct; with-replacement
comparisons can reuse controls and are not unique person counts.

The mentorship-period LPM includes direct_percent and log_PeerCount, logged mentor
h-index, logged training network size, logged annual total publication rate during
training, and effective-graduation-year fixed effects. Its sample is defined from
the training outcome and these predictors without requiring post-graduation
continuity measures. Its standard errors are clustered by mentee.

Overall-career trajectory groups require both period rates to be observed.
G1a has positive training output and a higher post-training rate; G1b has no
training output and positive post-training output. G2a has positive training
output and a post-training rate no higher than the training rate, including
unchanged rates. G2b has zero output in both periods.

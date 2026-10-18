# Author linkage and indicator construction

This directory provides reference code illustrating the linkage of Academic Family Tree (AFT) records with OpenAlex publication data and the construction of mentor–mentee indicators. The documentation describes the required data fields, linkage criteria, relationship selection and indicator definitions. The main analyses use the anonymized indicator tables supplied in `Data/`.

## Source data

Mentorship relationships and researcher information are drawn from the Academic Family Tree dataset (Ke et al., 2022). Publication and citation information is based on the May 30, 2025 OpenAlex snapshot.

The reference implementation uses the following source tables:

| Source | File | Required fields |
|---|---|---|
| AFT | `researcher.csv` | PID, FirstName, MiddleName, LastName, ORCID |
| AFT | `authorship.csv` | PID, MAGPaperID |
| AFT | `paper.csv` | MAGPaperID, DOI, PMID |
| AFT | `mentorship.csv` | MenteeID, MentorID, StartYear, StopYear |
| OpenAlex | `authors/author_ids.tsv` | author_id, orcid |
| OpenAlex | `authors/author_info.tsv` | author_id, display_name |
| OpenAlex | `authors/author_display_name_alternatives.tsv` | author_id, display_name_alternatives |
| OpenAlex | `works/paper_ids.tsv` | paper_id, mag_id, doi, pmid |
| OpenAlex | `works/paper_author_raw_affiliations.tsv` or `paper_author_affiliations.tsv` | paper_id, author_id |
| OpenAlex | `works/paper_info.tsv` | paper_id, publication_year, publication_date, source_id, cited_by_count |
| OpenAlex | `works/paper_primary_topic.tsv` | paper_id, topic_id |
| OpenAlex | `works/paper_referenced_works.tsv` | paper_id, reference_id |
| OpenAlex | `sources/source_info.tsv` | source_id, type, 2yr_mean_citedness, h_index, cited_by_count |

The OpenAlex input fields follow the cleaned TSV table schema. AFT person identifiers (`PID`) distinguish researcher records, while MAG identifiers, DOIs and PMIDs provide links between publication records.

## Author linkage

`link_authors.py` implements author identification using researcher identifiers, normalized names and linked publication records.

First, AFT publications are associated with OpenAlex works through MAG identifiers, DOIs and PMIDs. Ambiguous or conflicting publication correspondences remain unresolved.

Author identification then proceeds through the following steps:

1. **ORCID matching.** Valid, uniquely corresponding ORCID identifiers establish initial researcher–author assignments.
2. **Name matching.** Normalized names and available name variants identify candidate OpenAlex authors.
3. **Publication-based disambiguation.** Candidate assignments are evaluated using author intersections across linked publications.
4. **Iterative resolution.** Uniquely identifiable remaining authors can resolve additional assignments. Assigned authors are excluded from subsequent matching rounds, with up to six rounds by default.

Conflicting assignments of one OpenAlex author to multiple AFT researchers are excluded. Name-only assignments without publication evidence are optional and disabled by default. The resulting crosswalk associates AFT person identifiers with OpenAlex author identifiers. 

## Publication information and source classification

`collect_publications.py` organizes linked publication records, including publication years and dates, source identifiers, research topics, authorship and citation information. Repeated author–publication records arising from multiple affiliations are deduplicated.

Primary OpenAlex topics are used by default. Publication dates after the snapshot date are excluded.

Citation-elite journals are identified using three source-level indicators: two-year mean citedness, source h-index and total citation count. For each indicator, the 95th percentile is calculated from available nonnegative values across all source types using linear interpolation. Sources must be classified as journals and exceed all three thresholds.

## Relationship selection and indicator construction

`construct_pair_indicators.py` constructs relationship-level measures from the mentorship records and linked publication information.

Relationship records require valid researcher identifiers and usable start and end years, with `StopYear` not earlier than `StartYear`. Duplicate records sharing the same mentee, mentor, start year and end year are removed. No restriction is applied by mentorship type.

The analysis requires each mentee to have at least one publication during the extended mentorship period.

For publication lag \(t\), the extended mentorship period covers `StartYear` through `StopYear + t`. The analytical specifications use two-year and three-year extensions.

Conventional outcome windows cover the following 5, 10 or 20 years. Overall-career exposure ends at the last observed publication year. Landmark specifications measure continuity in years 1–3 after the effective boundary and publication outcomes in years 4–10 or 6–20.

The principal indicators are defined as follows:

| Indicator | Calculation |
|---|---|
| `topic_continuity` | Share of distinct mentorship-period primary topics also observed in the subsequent measurement period |
| `network_consistency` | Share of other coauthors from joint mentor–mentee mentorship-period publications retained in the subsequent measurement period |
| `direct_percent` | Mentor–mentee joint publications divided by all mentee publications during the extended mentorship period |
| `PeerCount` | Number of other mentees sharing the mentor with overlapping extended mentorship intervals |
| `NetworkSize_Mentored` | Number of distinct coauthors across the mentee's mentorship-period publications, excluding the mentee |
| `PaperCount_Mentored` | Total mentee publications during the extended mentorship period |
| `AvgPaperPerYear_Mentored` | Mentorship-period publication count divided by the corresponding exposure years |
| `h_index` | Mentor h-index calculated from publications and dated citations through the year preceding the recorded mentorship start |
| `TopPub_Mentored` | Citation-elite journal publication count during the extended mentorship period |
| `TopPub_Post` / `TopPub_Outcome` | Citation-elite journal publication counts within the corresponding outcome windows |

Publication counts, rates and exposure periods are retained as analytical inputs. Subsequent regressions and matching analyses apply their own eligibility and complete-case restrictions.

## Code organization

| Script | Function |
|---|---|
| `common.py` | Identifier normalization, data readers and shared indicator functions |
| `link_authors.py` | AFT–OpenAlex publication and author linkage |
| `collect_publications.py` | Linked publication collection, source classification and citation cache construction |
| `construct_pair_indicators.py` | Relationship filtering, temporal windows and indicator construction |
| `test_upstream.py` | Functional tests using synthetic input records |

The upstream code requires the corresponding external AFT and OpenAlex source tables. These raw records are not part of the review package. The statistical analyses and figures are reproduced separately from the supplied anonymized indicator tables, as described in the root `README.md`.

## References

Ke et al. (2022). https://doi.org/10.1038/s41597-022-01578-x

Academic Family Tree data: https://doi.org/10.5281/zenodo.4917086

Miura et al. (2025). https://doi.org/10.51408/issi2025_096
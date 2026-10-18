"""Synthetic tests for author linkage and publication-based indicators."""
from pathlib import Path
import json
import tempfile
import unittest

from common import h_index, orcid, read_mapping, topic_retention, write_csv
from link_authors import construct_linkage
from collect_publications import build_cache
from construct_pair_indicators import PublicationCache, build_indicators, clean_relationships, construct_metrics, has_joint_publication


def synthetic_orcid(n):
    prefix=f'{n:015d}'
    total=0
    for c in prefix:
        total=(total+int(c))*2
    last=(12-total%11)%11
    raw=prefix+('X' if last==10 else str(last))
    return '-'.join(raw[i:i+4] for i in range(0,16,4))


def fixture(root,unknown_citation=False):
    aft,oa=root/'aft',root/'openalex'
    for p in [aft,oa/'authors',oa/'works',oa/'sources']:
        p.mkdir(parents=True,exist_ok=True)
    people=[dict(PID=str(i),FirstName=f,MiddleName='',LastName=l,ORCID=o) for i,f,l,o in [
        (1,'Mentor','One',synthetic_orcid(1)),(2,'Mentee','Two',''),(3,'Peer','Three',''),
        (4,'Duplicate','Four',synthetic_orcid(2)),(5,'Duplicate','Five',synthetic_orcid(2)),
        (6,'Alex','Same',''),(7,'Unknown','Name',''),(8,'Name','Only','')]]
    write_csv(aft/'researcher.csv',people)
    pairs=[dict(MenteeID='2',MentorID='1',StartYear=2000,StopYear=2002,MentorshipType=1),
           dict(MenteeID='3',MentorID='1',StartYear=2001,StopYear=2003,MentorshipType=1)]
    write_csv(aft/'mentorship.csv',pairs+[pairs[0],dict(MenteeID='4',MentorID='1',StartYear=-1,StopYear=2005,MentorshipType=1),
                                             dict(MenteeID='5',MentorID='1',StartYear=2005,StopYear=2000,MentorshipType=2)])
    write_csv(aft/'authorship.csv',[dict(PID=str(pid),MAGPaperID=str(mag)) for pid,mag in [(1,10),(2,20),(3,30),(6,61),(6,99),(7,70),(7,71)]])
    write_csv(aft/'paper.csv',[dict(MAGPaperID=str(mag),DOI='10.9999/conflict' if mag==99 else '',PMID='')
                              for mag in [10,20,30,61,99,70,71]])
    authors=[dict(author_id=f'A{i}',display_name=n,works_count=1,cited_by_count=0) for i,n in [
        (1,'Mentor One'),(2,'Mentee Two'),(3,'Peer III'),(4,'Duplicate Four'),(6,'Alex Same'),
        (7,'Alex Same'),(8,'Unrelated Eight'),(9,'Unrelated Nine'),(10,'Unrelated Ten'),(11,'Name Only')]]
    write_csv(oa/'authors/author_info.csv',authors)
    write_tsv(oa/'authors/author_info.tsv',authors)
    write_tsv(oa/'authors/author_ids.tsv',[dict(author_id='A1',orcid=synthetic_orcid(1)),dict(author_id='A4',orcid=synthetic_orcid(2))])
    write_tsv(oa/'authors/author_display_name_alternatives.tsv',[dict(author_id='A3',display_name_alternatives='Peer Three')])
    identifiers=[dict(paper_id=f'W{i}',mag_id=str(i),doi='',pmid='') for i in [10,11,12,20,21,22,23,24,25,30,61,70,71,99]]
    identifiers.append(dict(paper_id='W100',mag_id='100',doi='10.9999/conflict',pmid=''))
    write_tsv(oa/'works/paper_ids.tsv',identifiers)
    author_works={10:[1],11:[1],12:[1],20:[1,2,3],21:[1,2,4],22:[2,3,5],23:[2,6],24:[2,7],
                  25:[2,4],30:[1,3],61:[6,7],70:[8,9],71:[8,10],99:[6]}
    records=[dict(paper_id=f'W{w}',author_id=f'A{a}',institution_id='I1') for w,ids in author_works.items() for a in ids]
    # Duplicate affiliation rows must not duplicate authorships.
    write_tsv(oa/'works/paper_author_affiliations.tsv',records+[records[0]])
    years={10:1990,11:1995,12:2001,20:2000,21:2002,22:2006,23:2007,24:2008,25:2010,30:2002,
           61:2000,70:1990,71:1991,99:2000,100:1999,101:1999,102:2002,103:2024,104:1996,90:1980}
    info=[dict(paper_id=f'W{w}',publication_year=y,publication_date=f'{y}-01-01',source_id='S1' if w in [20,21,22,25] else 'S2',
               cited_by_count=50 if w==10 else 100 if w==11 else 1000 if w==12 else 0) for w,y in years.items()]
    write_tsv(oa/'works/paper_info.tsv',info)
    topics={20:1,21:2,22:1,23:3,24:4,25:5,10:1,11:2,12:3,30:1,61:2,70:1,71:2,99:1}
    write_tsv(oa/'works/paper_primary_topic.tsv',[dict(paper_id=f'W{w}',topic_id=f'T{t}') for w,t in topics.items()])
    references=[(100,10),(100,11),(101,10),(102,11),(103,10),(103,11),(104,11),(100,10),(90,11)]
    if unknown_citation:
        references.append((199,10))
    write_tsv(oa/'works/paper_referenced_works.tsv',[dict(paper_id=f'W{c}',reference_id=f'W{r}') for c,r in references])
    write_tsv(oa/'sources/source_info.tsv',[dict(source_id=f'S{i}',type='journal',
        **{'2yr_mean_citedness':100 if i==1 else 0,'h_index':100 if i==1 else 0,'cited_by_count':1000000 if i==1 else 0}) for i in range(1,21)])
    return aft,oa


def write_tsv(path,records):
    import csv
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]),delimiter='\t')
        writer.writeheader();writer.writerows(records)


class UpstreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='synthetic_',dir=Path(__file__).resolve().parent)
        cls.root=Path(cls.temp.name)
        assert cls.root.resolve().is_relative_to(Path(__file__).resolve().parent)
        cls.aft,cls.oa=fixture(cls.root)
        cls.mapping=construct_linkage(cls.aft,cls.oa,cls.root/'link')
        cls.cache_path=build_cache(cls.oa,cls.root/'link/pid_openalex_crosswalk.csv',cls.root/'cache')
        cls.cache=PublicationCache(cls.cache_path)

    @classmethod
    def tearDownClass(cls):
        cls.cache.con.close()
        cls.temp.cleanup()

    def test_orcid_and_conflict_quarantine(self):
        self.assertEqual(self.mapping['1'],'A1')
        self.assertNotIn('4',self.mapping);self.assertNotIn('5',self.mapping)
        self.assertEqual(orcid('0000-0001-6187-6610'),'0000-0001-6187-6610')
        self.assertEqual(orcid('0000-0001-6187-6611'),'')

    def test_name_alias_and_work_set_constraints(self):
        self.assertEqual(self.mapping['2'],'A2')
        self.assertEqual(self.mapping['3'],'A3')
        self.assertEqual(self.mapping['7'],'A8')
        self.assertNotIn('6',self.mapping)
        self.assertNotIn('8',self.mapping)

    def test_identifier_conflict_not_forced(self):
        from common import rows
        r=next(r for r in rows(self.root/'link/work_linkage_audit.csv') if r['MAGPaperID']=='99')
        self.assertEqual(r['status'],'identifier_conflict')
        self.assertEqual(r['OpenAlexWorkID'],'')

    def test_relationship_cleaning(self):
        spells,flow=clean_relationships(self.aft/'mentorship.csv')
        self.assertEqual(len(spells),2)
        self.assertEqual([s['remaining'] for s in flow],[5,5,4,3,2])

    def test_h_index_excludes_future_papers_and_future_citations(self):
        self.assertEqual(self.cache.mentor_h('1',1999),2)
        n=self.cache.con.execute("SELECT SUM(n) FROM citation_year_count WHERE cited='W10' AND year<=1999").fetchone()[0]
        self.assertEqual(n,2)
        self.assertEqual(h_index([10,8,5,4,3]),4)

    def test_topic_and_network_retention(self):
        spell=clean_relationships(self.aft/'mentorship.csv')[0][0]
        conventional=construct_metrics(self.cache,spell,3,(2006,2010),(2006,2010),1,{'S1'})
        self.assertEqual(conventional['topic_continuity'],.5)
        self.assertEqual(conventional['network_consistency'],1)
        self.assertEqual(conventional['direct_percent'],1)
        self.assertEqual(conventional['NetworkSize_Mentored'],3)
        landmark=construct_metrics(self.cache,spell,3,(2006,2008),(2009,2015),1,{'S1'})
        self.assertEqual(landmark['network_consistency'],.5)
        self.assertEqual(landmark['TopPub_Outcome'],1)
        self.assertEqual(landmark['OutcomeExposureYears'],7)

    def test_indicator_exports_and_source_percentiles(self):
        result=build_indicators(self.aft/'mentorship.csv',self.cache_path,self.root/'metrics')
        self.assertEqual(len(result),12)
        from common import rows
        manifest=list(rows(self.root/'metrics/dataset_manifest.csv'))
        self.assertEqual(len(manifest),12)
        self.assertEqual({int(r['gap']) for r in manifest if r['family']=='landmark'},{2,3})
        metadata=json.loads((self.root/'cache/cache_metadata.json').read_text())
        self.assertEqual(metadata['elite_journal_count'],1)
        self.assertAlmostEqual(metadata['calculated_percentile_thresholds']['mean2'],5.0)
        self.assertAlmostEqual(metadata['calculated_percentile_thresholds']['h_index'],5.0)
        self.assertAlmostEqual(metadata['calculated_percentile_thresholds']['cited_by'],50000.0)

    def test_joint_publication_after_recorded_end_does_not_qualify(self):
        spell=dict(MenteeID='2',MentorID='3',StartYear=2001,StopYear=2005)
        self.assertFalse(has_joint_publication(self.cache,spell))
        extended=construct_metrics(self.cache,spell,3,(2009,2013),(2009,2013),0,{'S1'})
        self.assertGreater(extended['DirectJointPaperCount'],0)

    def test_topic_retention_denominator(self):
        self.assertEqual(topic_retention({'T1','T2'},{'T1','T3','T4'}),.5)
        self.assertEqual(topic_retention({'T1'},set()),0)
        self.assertIsNone(topic_retention(set(),{'T1'}))

    def test_joint_publication_filter_excludes_zero_joint_spells(self):
        from common import rows
        source=list(rows(self.aft/'mentorship.csv'))
        source.append(dict(MenteeID='2',MentorID='7',StartYear='2000',StopYear='2002',MentorshipType='1'))
        path=self.root/'mentorship_with_zero_joint.csv'
        write_csv(path,source)
        destination=self.root/'joint_only'
        build_indicators(path,self.cache_path,destination,require_joint=True)
        tables=list(destination.glob('*.csv.gz'))
        if not tables:
            tables=list(destination.glob('*.csv'))
        self.assertTrue(tables)
        retained=0
        for table in tables:
            for row in rows(table):
                if 'DirectJointPaperCount' in row:
                    self.assertGreater(float(row['DirectJointPaperCount']),0)
                    retained+=1
        self.assertGreater(retained,0)

    def test_cleaned_crosswalk_column(self):
        path=self.root/'cleaned_crosswalk.csv'
        write_csv(path,[dict(PID='1',author_OpenAlex_id='https://openalex.org/A1'),
                        dict(PID='2',author_OpenAlex_id='A2')])
        self.assertEqual(read_mapping(path),{'1':'A1','2':'A2'})

    def test_crosswalk_without_valid_assignments_is_rejected(self):
        path=self.root/'empty_crosswalk.csv'
        write_csv(path,[dict(PID='1',author_OpenAlex_id='')])
        with self.assertRaisesRegex(ValueError,'No valid PID'):
            read_mapping(path)

    def test_unknown_citation_year_does_not_become_zero(self):
        aft,oa=fixture(self.root/'missing_date',unknown_citation=True)
        p=build_cache(oa,self.root/'link/pid_openalex_crosswalk.csv',self.root/'unknown_cache')
        cache=PublicationCache(p)
        self.assertIsNone(cache.mentor_h('1',1999))
        cache.con.close()

    def test_zero_collaboration_is_not_automatically_a_missing_direct_percent(self):
        spell=dict(MenteeID='2',MentorID='7',StartYear=2000,StopYear=2002)
        result=construct_metrics(self.cache,spell,3,(2006,2010),(2006,2010),0,{'S1'})
        self.assertEqual(result['direct_percent'],0)
        self.assertIsNone(result['network_consistency'])
        zero=construct_metrics(self.cache,spell,3,(2006,2010),(2006,2010),0,{'S1'},empty_network='zero')
        self.assertEqual(zero['network_consistency'],0)

    def test_undated_works_do_not_produce_observed_partial_collaboration(self):
        from common import rows
        aft,oa=fixture(self.root/'undated_work')
        info=list(rows(oa/'works/paper_info.tsv'))
        for row in info:
            if row['paper_id']=='W21':
                row['publication_year']='';row['publication_date']=''
        write_tsv(oa/'works/paper_info.tsv',info)
        p=build_cache(oa,self.root/'link/pid_openalex_crosswalk.csv',self.root/'undated_cache')
        cache=PublicationCache(p)
        spell=clean_relationships(aft/'mentorship.csv')[0][0]
        result=construct_metrics(cache,spell,3,(2006,2010),(2006,2010),1,{'S1'})
        self.assertIsNone(result['direct_percent'])
        self.assertIsNone(result['network_consistency'])
        self.assertIsNone(result['topic_continuity'])
        cache.con.close()


if __name__=='__main__':
    unittest.main(verbosity=2)

"""Calculate topic retention, collaboration measures and pre-start mentor h-index."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from common import h_index, integer, rows, topic_retention, value, write_csv


def clean_relationships(path):
    source = list(rows(path))
    identified = [r for r in source if value(r,'MenteeID') and value(r,'MentorID') not in {'','0'}]
    dated = []
    for r in identified:
        start, stop = integer(value(r,'StartYear')), integer(value(r,'StopYear'))
        if start is not None and stop is not None and start!=-1 and stop!=-1:
            dated.append(dict(MenteeID=value(r,'MenteeID'), MentorID=value(r,'MentorID'),
                              StartYear=start, StopYear=stop, MentorshipType=value(r,'MentorshipType')))
    ordered = [r for r in dated if r['StopYear']>=r['StartYear']]
    unique = {}
    for r in ordered:
        key = (r['MenteeID'],r['MentorID'],r['StartYear'],r['StopYear'])
        unique.setdefault(key,r)
    flow = [dict(step='Source relationships',remaining=len(source),excluded=0),
            dict(step='Usable person identifiers',remaining=len(identified),excluded=len(source)-len(identified)),
            dict(step='Usable start/end years',remaining=len(dated),excluded=len(identified)-len(dated)),
            dict(step='Valid year order',remaining=len(ordered),excluded=len(dated)-len(ordered)),
            dict(step='Distinct relationship spells',remaining=len(unique),excluded=len(ordered)-len(unique))]
    return list(unique.values()), flow


class PublicationCache:
    def __init__(self,path):
        self.path=Path(path)
        self.con=sqlite3.connect(f'file:{self.path.resolve().as_posix()}?mode=ro',uri=True)
        self.con.row_factory=sqlite3.Row
        self.metadata=json.loads((self.path.parent/'cache_metadata.json').read_text(encoding='utf-8'))
        self.snapshot=self.metadata['snapshot_date']
        self.year=int(self.snapshot[:4])
        self.mapping=dict(self.con.execute('SELECT pid,author_id FROM person'))

    @lru_cache(maxsize=8192)
    def publications(self,pid):
        author=self.mapping.get(pid)
        if not author:
            return ()
        items=self.con.execute('''SELECT w.* FROM author_work a LEFT JOIN work w USING(work_id)
                                WHERE a.author_id=? ORDER BY w.work_id''',(author,)).fetchall()
        return tuple(dict(r) for r in items)

    def observed(self,pid):
        return [r for r in self.publications(pid) if r['year'] is not None and r['metadata_present']
                and r['year']<=self.year and (not r['publication_date'] or r['publication_date']<=self.snapshot)]

    def complete_dates(self,pid):
        return pid in self.mapping and all(r['year'] is not None and r['metadata_present'] for r in self.publications(pid))

    @lru_cache(maxsize=30000)
    def authors(self,work):
        return frozenset(r[0] for r in self.con.execute('SELECT author_id FROM work_author WHERE work_id=?',(work,)))

    @lru_cache(maxsize=30000)
    def topics(self,work):
        return frozenset(r[0] for r in self.con.execute('SELECT topic_id FROM work_topic WHERE work_id=?',(work,)))

    @lru_cache(maxsize=65536)
    def mentor_h(self,pid,cutoff):
        if not self.metadata['historical_citation_graph_loaded']:
            raise ValueError('Pre-start h-index cannot be calculated without dated incoming-reference data')
        if not self.complete_dates(pid):
            return None
        counts=[]
        for work in self.observed(pid):
            if work['year']>cutoff:
                continue
            unknown=self.con.execute('SELECT n FROM citation_unknown_date WHERE cited=?',(work['work_id'],)).fetchone()
            if unknown and unknown[0]>0:
                return None
            n=self.con.execute('SELECT COALESCE(SUM(n),0) FROM citation_year_count WHERE cited=? AND year<=?',
                               (work['work_id'],cutoff)).fetchone()[0]
            counts.append(int(n))
        return h_index(counts)


def in_period(papers,start,end):
    return [p for p in papers if start<=p['year']<=end]


def sets_for(cache,papers,attribute):
    function=getattr(cache,attribute)
    result=set()
    covered=0
    for p in papers:
        values=function(p['work_id'])
        if values:
            covered+=1
        result.update(values)
    return result, covered


def construct_metrics(cache,spell,gap,measurement,end,peer_count,elite,empty_network='missing',minimum_author_coverage=.95):
    mentee, mentor=spell['MenteeID'],spell['MentorID']
    effective=spell['StopYear']+gap
    known=cache.complete_dates(mentee)
    papers=cache.observed(mentee)
    training=in_period(papers,spell['StartYear'],effective)
    later=in_period(papers,*measurement)
    outcome=in_period(papers,*end)
    training_ids={p['work_id'] for p in training}
    if training_ids & {p['work_id'] for p in later} or training_ids & {p['work_id'] for p in outcome}:
        raise ValueError('Overlapping mentorship and post-mentorship publication periods')
    training_topics,tcovered=sets_for(cache,training,'topics')
    later_topics,lcovered=sets_for(cache,later,'topics')
    retention=topic_retention(training_topics,later_topics)
    if (later and not later_topics) or not known:
        retention=None
    mentor_author=cache.mapping.get(mentor)
    mentee_author=cache.mapping.get(mentee)
    training_authors,training_covered=sets_for(cache,training,'authors')
    later_authors,later_covered=sets_for(cache,later,'authors')
    training_coverage=training_covered/len(training) if training else None
    later_coverage=later_covered/len(later) if later else 1.0
    jointly=[p for p in training if mentor_author and mentor_author in cache.authors(p['work_id'])]
    direct=len(jointly)/len(training) if known and training and mentor_author and training_coverage>=minimum_author_coverage else None
    joint_authors,_=sets_for(cache,jointly,'authors')
    joint_authors-={mentee_author,mentor_author}
    later_authors-={mentee_author,mentor_author}
    net=None
    if known and mentor_author and mentee_author and training and training_coverage>=minimum_author_coverage and later_coverage>=minimum_author_coverage:
        net=len(joint_authors & later_authors)/len(joint_authors) if joint_authors else (0.0 if empty_network=='zero' else None)
    training_authors.discard(mentee_author)
    training_span=effective-spell['StartYear']+1
    exposure=end[1]-end[0]+1
    mentored_elite=sum(p['source_id'] in elite for p in training) if known else None
    output_elite=sum(p['source_id'] in elite for p in outcome) if known else None
    return dict(EffectiveGraduationYear=effective,
                topic_continuity=retention,
                network_consistency=net,direct_percent=direct,PeerCount=peer_count,log_PeerCount=math.log1p(peer_count),
                h_index=cache.mentor_h(mentor,spell['StartYear']-1),
                PaperCount_Mentored=len(training) if known else None,
                AvgPaperPerYear_Mentored=len(training)/training_span if known else None,
                TopPub_Mentored=mentored_elite,
                AvgTopPubPerYear_Mentored=mentored_elite/training_span if mentored_elite is not None else None,
                NetworkSize_Mentored=len(training_authors) if known and training and training_coverage>=minimum_author_coverage else None,
                DirectJointPaperCount=len(jointly) if direct is not None else None,
                PaperCount_Capability=len(later) if known else None,
                TopicCoverage_Mentored=tcovered/len(training) if training else None,
                TopicCoverage_Measurement=lcovered/len(later) if later else None,
                AuthorCoverage_Mentored=training_coverage,
                TopPub_Outcome=output_elite,
                AvgTopPubPerYear_Outcome=output_elite/exposure if output_elite is not None and exposure>0 else None,
                OutcomeExposureYears=exposure,
                MenteeMapped=int(bool(mentee_author)),MentorMapped=int(bool(mentor_author)),
                PublicationDatesComplete=int(known))


def has_joint_publication(cache, spell):
    mentor=cache.mapping.get(spell['MentorID'])
    mentee=cache.mapping.get(spell['MenteeID'])
    if not mentor or not mentee:
        return False
    return any(spell['StartYear']<=p['year']<=spell['StopYear']
               and {mentor,mentee}.issubset(cache.authors(p['work_id']))
               for p in cache.observed(spell['MenteeID']))


def build_indicators(mentorship,cache_path,output,empty_network='missing',minimum_author_coverage=.95,require_joint=True):
    if not 0<=minimum_author_coverage<=1:
        raise ValueError('Author coverage threshold must be between zero and one')
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    spells,flow=clean_relationships(mentorship)
    cache=PublicationCache(cache_path)
    if not cache.metadata['historical_citation_graph_loaded']:
        raise ValueError('Pre-start h-index requires a historical citation cache')
    candidate_count=len(spells)
    if require_joint:
        spells=[spell for spell in spells if has_joint_publication(cache,spell)]
        flow.append(dict(step='Joint publication during recorded mentorship',remaining=len(spells),excluded=candidate_count-len(spells)))
    write_csv(output/'source_relationship_cleaning.csv',flow)
    people=sorted({r[k] for r in spells for k in ['MenteeID','MentorID']})
    people_ids={pid:f'P{i:06d}' for i,pid in enumerate(people,1)}
    ordered=sorted(spells,key=lambda r:(r['MenteeID'],r['MentorID'],r['StartYear'],r['StopYear']))
    spell_ids={(r['MenteeID'],r['MentorID'],r['StartYear'],r['StopYear']):f'R{i:06d}' for i,r in enumerate(ordered,1)}
    mentor_spells=defaultdict(list)
    for spell in spells:
        mentor_spells[spell['MentorID']].append(spell)
    peers={}
    for gap in (2,3):
        for spell in spells:
            other={s['MenteeID'] for s in mentor_spells[spell['MentorID']]
                   if s['MenteeID']!=spell['MenteeID'] and s['StartYear']<=spell['StopYear']+gap
                   and s['StopYear']+gap>=spell['StartYear']}
            key=(spell['MenteeID'],spell['MentorID'],spell['StartYear'],spell['StopYear'],gap)
            peers[key]=len(other)
    elite={r[0] for r in cache.con.execute('SELECT source_id FROM source WHERE elite=1')}
    handles,writers,counts={}, {},defaultdict(int)
    def emit(family,gap,horizon,spell,metrics):
        key=(spell['MenteeID'],spell['MentorID'],spell['StartYear'],spell['StopYear'])
        row=dict(PairID=spell_ids[key],MenteeID=people_ids[spell['MenteeID']],MentorID=people_ids[spell['MentorID']],**metrics)
        if family!='landmark':
            row['TopPub_Post']=row.pop('TopPub_Outcome')
            row['AvgTopPubPerYear_Post']=row.pop('AvgTopPubPerYear_Outcome')
            row['PostCareerYears' if family=='overall' else 'PostWindowYears']=row.pop('OutcomeExposureYears')
        name=f'{family}_t{gap}_{horizon}.csv'
        if name not in writers:
            handle=(output/name).open('w',encoding='utf-8',newline='')
            handles[name]=handle
            writers[name]=csv.DictWriter(handle,fieldnames=list(row))
            writers[name].writeheader()
        writers[name].writerow({k:'' if v is None else v for k,v in row.items()})
        counts[name]+=1
    try:
        for i,spell in enumerate(spells,1):
            known=cache.observed(spell['MenteeID'])
            for gap in (2,3):
                effective=spell['StopYear']+gap
                peer=peers[spell['MenteeID'],spell['MentorID'],spell['StartYear'],spell['StopYear'],gap]
                for years in (5,10,20):
                    if effective+years<=cache.year:
                        period=(effective+1,effective+years)
                        emit('conventional',gap,f'L{years}',spell,
                             construct_metrics(cache,spell,gap,period,period,peer,elite,empty_network,minimum_author_coverage))
                if known:
                    latest=max(p['year'] for p in known)
                    period=(effective+1,max(effective,latest))
                    emit('overall',gap,'overall_career',spell,
                         construct_metrics(cache,spell,gap,period,period,peer,elite,empty_network,minimum_author_coverage))
                for first,last in [(4,10),(6,20)]:
                    if effective+last<=cache.year:
                        measure=(effective+1,effective+3)
                        end=(effective+first,effective+last)
                        if measure[1]>=end[0]:
                            raise ValueError('Landmark measurement and outcome periods overlap')
                        emit('landmark',gap,f'early1_3_to_later{first}_{last}',spell,
                             construct_metrics(cache,spell,gap,measure,end,peer,
                                               elite,empty_network,minimum_author_coverage))
            if i%1000==0:
                print(f'Constructed {i:,}/{len(spells):,} relationship spells',flush=True)
    finally:
        for handle in handles.values():
            handle.close()
        cache.con.close()
    definitions=dict(implementation='topic_retention_pre_start_h', topic_continuity='training-topic retained share',
                     topic_mode=cache.metadata['topic_mode'],h_index='Calculated from mentor works and unique citing works through StartYear-1',
                     mentorship_publication_count='PaperCount_Mentored', annual_mentorship_publication_rate='AvgPaperPerYear_Mentored',
                     empty_network=empty_network,require_joint_publication=require_joint,
                     minimum_author_coverage=minimum_author_coverage,snapshot_date=cache.snapshot,
                     candidate_spells=candidate_count,collaboration_eligible_spells=len(spells),
                     joint_publication_period='StartYear through StopYear',output_rows=dict(counts))
    (output/'construction_metadata.json').write_text(json.dumps(definitions,indent=2),encoding='utf-8')
    manifest=[]
    for name,count in sorted(counts.items()):
        family,lag,horizon=Path(name).stem.split('_',2)
        landmark=family=='landmark'
        manifest.append(dict(family=family,gap=int(lag[1:]),horizon=horizon,
                             file='Data/'+name,input_rows=count,
                             count_outcome='TopPub_Outcome' if landmark else 'TopPub_Post',
                             rate_outcome='AvgTopPubPerYear_Outcome' if landmark else 'AvgTopPubPerYear_Post',
                             exposure='OutcomeExposureYears' if landmark else 'PostCareerYears' if family=='overall' else 'PostWindowYears',
                             sha256=hashlib.sha256((output/name).read_bytes()).hexdigest()))
    write_csv(output/'dataset_manifest.csv',manifest)
    return counts


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mentorship',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--empty-network',choices=['missing','zero'],default='missing')
    parser.add_argument('--minimum-author-coverage',type=float,default=.95)
    parser.add_argument('--require-joint-publication',action='store_true',default=True)
    args=parser.parse_args()
    build_indicators(args.mentorship,args.cache,args.output,args.empty_network,args.minimum_author_coverage,args.require_joint_publication)

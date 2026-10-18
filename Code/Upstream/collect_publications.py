"""Collect selected publication metadata and historical incoming-reference counts."""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path

import numpy as np
from common import database, insert_batches, integer, number, oa_id, read_mapping, rows, value, write_csv


def build_cache(openalex_root, crosswalk, output, snapshot_date='2025-05-30', historical=True, topic_mode='primary'):
    openalex_root, output = Path(openalex_root), Path(output)
    snapshot = date.fromisoformat(snapshot_date)
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'publication_cache.sqlite'
    if path.exists():
        raise FileExistsError('Use a fresh output directory; publication cache exists')
    mapping = read_mapping(crosswalk)
    selected_authors = set(mapping.values())
    con = database(path)
    con.executescript('''
      CREATE TABLE person(pid TEXT PRIMARY KEY, author_id TEXT);
      CREATE TABLE author_work(author_id TEXT, work_id TEXT, PRIMARY KEY(author_id,work_id));
      CREATE TABLE work(work_id TEXT PRIMARY KEY, year INTEGER, publication_date TEXT,
                        source_id TEXT, cited_by_count INTEGER, metadata_present INTEGER DEFAULT 0);
      CREATE TABLE work_author(work_id TEXT, author_id TEXT, PRIMARY KEY(work_id,author_id));
      CREATE TABLE work_topic(work_id TEXT, topic_id TEXT, PRIMARY KEY(work_id,topic_id));
      CREATE TABLE source(source_id TEXT PRIMARY KEY, type TEXT, mean2 REAL, h_index REAL, cited_by REAL, elite INTEGER);
      CREATE TABLE citation(citing TEXT, cited TEXT, PRIMARY KEY(citing,cited));
      CREATE TABLE citing_id(work_id TEXT PRIMARY KEY);
      CREATE TABLE citing_date(work_id TEXT PRIMARY KEY, year INTEGER, publication_date TEXT);
      CREATE TABLE citation_year_count(cited TEXT, year INTEGER, n INTEGER, PRIMARY KEY(cited,year));
      CREATE TABLE citation_unknown_date(cited TEXT PRIMARY KEY, n INTEGER);
    ''')
    con.executemany('INSERT INTO person VALUES (?,?)', mapping.items())
    con.commit()
    author_paths = [openalex_root/'works'/f for f in ['paper_author_raw_affiliations.tsv', 'paper_author_affiliations.tsv']]
    if not any(p.exists() for p in author_paths):
        raise FileNotFoundError('No work-authorship file')
    for f in author_paths:
        if f.exists():
            insert_batches(con, 'INSERT OR IGNORE INTO author_work VALUES (?,?)',
                           ((a,w) for r in rows(f) if (a := oa_id(value(r,'author_id'),'A')) in selected_authors
                            and (w := oa_id(value(r,'paper_id'),'W'))))
    con.execute('INSERT INTO work(work_id) SELECT DISTINCT work_id FROM author_work')
    con.commit()
    target_works = {r[0] for r in con.execute('SELECT work_id FROM work')}
    print(f'Selected work collection: {len(target_works):,}', flush=True)
    for f in author_paths:
        if f.exists():
            insert_batches(con, 'INSERT OR IGNORE INTO work_author VALUES (?,?)',
                           ((w,a) for r in rows(f) if (w := oa_id(value(r,'paper_id'),'W')) in target_works
                            and (a := oa_id(value(r,'author_id'),'A'))))
    references = openalex_root / 'works/paper_referenced_works.tsv'
    if historical and not references.exists():
        raise FileNotFoundError('Historical h-index requires paper_referenced_works.tsv')
    if historical:
        insert_batches(con, 'INSERT OR IGNORE INTO citation VALUES (?,?)',
                       ((citing,cited) for r in rows(references)
                        if (cited := oa_id(value(r,'reference_id'),'W')) in target_works
                        and (citing := oa_id(value(r,'paper_id'),'W')) and citing != cited))
        con.execute('INSERT INTO citing_id SELECT DISTINCT citing FROM citation')
        con.commit()
    # A temporary batch table updates selected and citing-work metadata. Full work
    # metadata are not loaded into RAM or retained wholesale in this cache.
    con.execute('CREATE TEMP TABLE batch_info(work_id TEXT PRIMARY KEY, year INTEGER, day TEXT, source_id TEXT, cited INTEGER)')
    batch = []
    scanned = 0
    def flush():
        if not batch:
            return
        con.execute('DELETE FROM batch_info')
        con.executemany('INSERT INTO batch_info VALUES (?,?,?,?,?)', batch)
        con.execute('''UPDATE work SET
           year=(SELECT b.year FROM batch_info b WHERE b.work_id=work.work_id),
           publication_date=(SELECT b.day FROM batch_info b WHERE b.work_id=work.work_id),
           source_id=(SELECT b.source_id FROM batch_info b WHERE b.work_id=work.work_id),
           cited_by_count=(SELECT b.cited FROM batch_info b WHERE b.work_id=work.work_id), metadata_present=1
           WHERE work_id IN (SELECT work_id FROM batch_info)''')
        if historical:
            con.execute('''INSERT OR REPLACE INTO citing_date
                SELECT b.work_id,b.year,b.day FROM batch_info b INNER JOIN citing_id i USING(work_id)''')
        con.commit()
        batch.clear()
    for row in rows(openalex_root/'works/paper_info.tsv'):
        work = oa_id(value(row,'paper_id','id'),'W')
        if not work:
            continue
        year, citations = integer(value(row,'publication_year')), integer(value(row,'cited_by_count'))
        day = value(row,'publication_date')
        if day:
            try:
                day = date.fromisoformat(day[:10]).isoformat()
                if year is not None and int(day[:4]) != year:
                    raise ValueError(f'Inconsistent publication year/date for {work}')
            except ValueError:
                raise ValueError(f'Invalid or inconsistent publication date for {work}')
        batch.append((work, year, day, oa_id(value(row,'source_id'),'S'), citations if citations is not None and citations>=0 else None))
        scanned += 1
        if len(batch)>=20000:
            flush()
    flush()
    topic_path = openalex_root / 'works' / ('paper_primary_topic.tsv' if topic_mode=='primary' else 'paper_topics.tsv')
    insert_batches(con, 'INSERT OR IGNORE INTO work_topic VALUES (?,?)',
                   ((w,t) for r in rows(topic_path) if (w := oa_id(value(r,'paper_id'),'W')) in target_works
                    and (t := oa_id(value(r,'topic_id'),'T'))))
    if topic_mode=='primary' and con.execute('SELECT work_id FROM work_topic GROUP BY work_id HAVING COUNT(*)>1 LIMIT 1').fetchone():
        raise ValueError('Conflicting primary topics: the supplied table is not one primary topic per work')
    source_records = []
    for row in rows(openalex_root/'sources/source_info.tsv'):
        sid = oa_id(value(row,'source_id','id'),'S')
        if sid:
            source_records.append(dict(source_id=sid, type=value(row,'type'),
                                       mean2=number(value(row,'2yr_mean_citedness')),
                                       h_index=number(value(row,'h_index')), cited_by=number(value(row,'cited_by_count'))))
    # Percentiles over all sources, each metric's available values separately.
    thresholds = {}
    for key in ['mean2','h_index','cited_by']:
        available=[r[key] for r in source_records if r[key] is not None and r[key]>=0]
        if not available:
            raise ValueError(f'No usable source values for {key}; check cleaned source_info.tsv schema')
        thresholds[key]=float(np.quantile(available,.95,method='linear'))
    elite = 0
    for r in source_records:
        r['elite'] = int(r['type']=='journal' and all(r[k] is not None and r[k]>thresholds[k] for k in thresholds))
        elite += r['elite']
    con.executemany('INSERT INTO source VALUES (:source_id,:type,:mean2,:h_index,:cited_by,:elite)', source_records)
    con.commit()
    if historical:
        con.execute('CREATE INDEX citation_by_cited ON citation(cited,citing)')
        con.execute('''INSERT INTO citation_year_count
           SELECT c.cited,d.year,COUNT(*) FROM citation c
           JOIN citing_date d ON c.citing=d.work_id JOIN work w ON c.cited=w.work_id
           WHERE d.year IS NOT NULL AND w.year IS NOT NULL AND d.year>=w.year AND d.year<=?
             AND (d.publication_date='' OR d.publication_date<=?)
           GROUP BY c.cited,d.year''', (snapshot.year, snapshot.isoformat()))
        con.execute('''INSERT INTO citation_unknown_date
           SELECT c.cited,COUNT(*) FROM citation c LEFT JOIN citing_date d ON c.citing=d.work_id
           WHERE d.year IS NULL GROUP BY c.cited''')
        con.commit()
    missing_metadata = con.execute('SELECT COUNT(*) FROM work WHERE metadata_present=0').fetchone()[0]
    summary = dict(snapshot_date=snapshot.isoformat(), historical_citation_graph_loaded=historical,
                   topic_mode=topic_mode, selected_people=len(mapping), selected_authors=len(selected_authors),
                   selected_works=len(target_works), work_info_rows_scanned=scanned,
                   selected_works_missing_metadata=missing_metadata, source_count=len(source_records),
                   elite_journal_count=elite, calculated_percentile_thresholds=thresholds)
    write_csv(output/'elite_sources.csv', [r for r in source_records if r['elite']])
    (output/'cache_metadata.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    con.close()
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--openalex-root',type=Path,required=True)
    parser.add_argument('--crosswalk',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--snapshot-date',default='2025-05-30')
    parser.add_argument('--topic-mode',choices=['primary','all'],default='primary')
    parser.add_argument('--without-historical-citations',action='store_true',help='Only publication metadata; historical h-index cannot then be constructed')
    args=parser.parse_args()
    build_cache(args.openalex_root,args.crosswalk,args.output,args.snapshot_date,not args.without_historical_citations,args.topic_mode)

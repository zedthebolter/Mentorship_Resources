"""Link AFT people to OpenAlex authors using ORCIDs, names and work sets."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from common import database, doi, insert_batches, name_key, oa_id, orcid, person_name_keys, pmid, rows, value, write_csv


def construct_linkage(aft_root, openalex_root, output, allow_name_only=False, max_rounds=6):
    if max_rounds<1:
        raise ValueError('max_rounds must be positive')
    aft_root, openalex_root, output = map(Path, [aft_root, openalex_root, output])
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / 'linkage_index.sqlite'
    if db_path.exists():
        raise FileExistsError('Use a fresh output directory; index already exists')
    people = {}
    strong, weak = {}, {}
    orcids = set()
    for row in rows(aft_root / 'researcher.csv'):
        pid = value(row, 'PID')
        if not pid or pid in people:
            raise ValueError('Missing or duplicated researcher PID')
        people[pid] = row
        strong[pid], weak[pid] = person_name_keys(row)
        key = orcid(value(row, 'ORCID'))
        if key:
            orcids.add(key)
    names = set().union(*strong.values(), *weak.values())
    con = database(db_path)
    con.executescript('''
      CREATE TABLE aft_authorship(pid TEXT, mag_id TEXT, PRIMARY KEY(pid,mag_id));
      CREATE TABLE aft_paper(mag_id TEXT PRIMARY KEY, doi TEXT, pmid TEXT);
      CREATE TABLE anchor(pid TEXT, work_id TEXT, PRIMARY KEY(pid,work_id));
      CREATE TABLE oa_name(name TEXT, author_id TEXT, PRIMARY KEY(name,author_id));
      CREATE TABLE oa_orcid(orcid TEXT, author_id TEXT, PRIMARY KEY(orcid,author_id));
      CREATE TABLE work_author(work_id TEXT, author_id TEXT, PRIMARY KEY(work_id,author_id));
    ''')
    insert_batches(con, 'INSERT OR IGNORE INTO aft_authorship VALUES (?,?)',
                   ((value(r, 'PID'), value(r, 'MAGPaperID')) for r in rows(aft_root/'authorship.csv')
                    if value(r, 'PID') in people and value(r, 'MAGPaperID').isdigit()))
    needed_mag = {r[0] for r in con.execute('SELECT DISTINCT mag_id FROM aft_authorship')}
    source_papers = {}
    for row in rows(aft_root / 'paper.csv'):
        mag = value(row, 'MAGPaperID')
        if mag in needed_mag:
            record = (doi(value(row, 'DOI')), pmid(value(row, 'PMID')))
            if mag in source_papers and source_papers[mag] != record:
                raise ValueError(f'Conflicting identifiers for MAG paper {mag}')
            source_papers[mag] = record
    target_keys = {'mag': needed_mag, 'doi': {r[0] for r in source_papers.values() if r[0]},
                   'pmid': {r[1] for r in source_papers.values() if r[1]}}
    matches = defaultdict(set)
    for row in rows(openalex_root / 'works/paper_ids.tsv'):
        work = oa_id(value(row, 'paper_id', 'openalex_id'), 'W')
        if not work:
            continue
        keys = {'mag': value(row, 'mag_id'), 'doi': doi(value(row, 'doi')), 'pmid': pmid(value(row, 'pmid'))}
        for kind, key in keys.items():
            if key and key in target_keys[kind]:
                matches[kind, key].add(work)
    paper_map, work_audit = {}, []
    for mag in sorted(needed_mag):
        d, p = source_papers.get(mag, ('', ''))
        sets = [matches[kind, key] for kind, key in [('mag', mag), ('doi', d), ('pmid', p)] if matches.get((kind, key))]
        shared = set.intersection(*sets) if sets else set()
        if len(shared) == 1:
            paper_map[mag] = next(iter(shared))
            status = 'unique_identifier_agreement'
        elif sets and not shared:
            status = 'identifier_conflict'
        else:
            status = 'ambiguous' if shared else 'unmatched'
        work_audit.append(dict(MAGPaperID=mag, OpenAlexWorkID=paper_map.get(mag, ''), status=status))
    write_csv(output / 'work_linkage_audit.csv', work_audit)
    insert_batches(con, 'INSERT OR IGNORE INTO anchor VALUES (?,?)',
                   ((pid, paper_map[mag]) for pid, mag in con.execute('SELECT pid,mag_id FROM aft_authorship') if mag in paper_map))
    print(f'Work anchors: {len(paper_map):,}', flush=True)
    for filename, column in [('author_info.tsv', 'display_name'), ('author_display_name_alternatives.tsv', 'display_name_alternatives')]:
        path = openalex_root / 'authors' / filename
        if not path.exists():
            if filename == 'author_info.tsv':
                raise FileNotFoundError(path)
            continue
        def name_records():
            for row in rows(path):
                author = oa_id(value(row, 'author_id'), 'A')
                raw = value(row, column)
                if raw.startswith('['):
                    try:
                        variants = json.loads(raw)
                    except json.JSONDecodeError:
                        variants = [raw]
                else:
                    variants = [raw]
                for variant in variants:
                    key = name_key(variant)
                    if author and key in names:
                        yield key, author
        insert_batches(con, 'INSERT OR IGNORE INTO oa_name VALUES (?,?)', name_records())
    def orcid_records():
        for row in rows(openalex_root / 'authors/author_ids.tsv'):
            key = orcid(value(row, 'orcid'))
            author = oa_id(value(row, 'author_id'), 'A')
            if key in orcids and author:
                yield key, author
    insert_batches(con, 'INSERT OR IGNORE INTO oa_orcid VALUES (?,?)', orcid_records())
    anchors = {r[0] for r in con.execute('SELECT DISTINCT work_id FROM anchor')}
    authorship_paths = [openalex_root / 'works' / f for f in ['paper_author_raw_affiliations.tsv', 'paper_author_affiliations.tsv']]
    if not any(p.exists() for p in authorship_paths):
        raise FileNotFoundError('No cleaned work-authorship table')
    for path in authorship_paths:
        if path.exists():
            insert_batches(con, 'INSERT OR IGNORE INTO work_author VALUES (?,?)',
                           ((w, a) for r in rows(path)
                            if (w := oa_id(value(r, 'paper_id'), 'W')) in anchors
                            and (a := oa_id(value(r, 'author_id'), 'A'))))
    mapping, evidence, quarantined = {}, {}, set()
    pending = set(people)
    def name_candidates(pid, strong_only=False):
        keys = strong[pid] if strong_only else strong[pid] | weak[pid]
        return set().union(*({r[0] for r in con.execute('SELECT author_id FROM oa_name WHERE name=?', (key,))} for key in keys)) if keys else set()
    def paper_sets(pid, occupied=None):
        sets = []
        for (work,) in con.execute('SELECT work_id FROM anchor WHERE pid=?', (pid,)):
            authors = {r[0] for r in con.execute('SELECT author_id FROM work_author WHERE work_id=?', (work,))}
            if authors:
                sets.append(authors - (occupied or set()) - quarantined)
        return sets
    proposals = {}
    for pid, person in people.items():
        key = orcid(value(person, 'ORCID'))
        candidates = {r[0] for r in con.execute('SELECT author_id FROM oa_orcid WHERE orcid=?', (key,))} if key else set()
        if len(candidates) == 1:
            proposals[pid] = (next(iter(candidates)), 'orcid_unique', 0)
        elif len(candidates) > 1:
            sets = paper_sets(pid)
            possible = candidates & (set.intersection(*sets) if sets else set())
            if len(possible) == 1:
                proposals[pid] = (next(iter(possible)), 'orcid_and_work_sets', 0)
    def accept(proposals):
        groups = defaultdict(list)
        for pid, (author, method, iteration) in proposals.items():
            groups[author].append(pid)
        for author, pids in groups.items():
            existing = [pid for pid, candidate in mapping.items() if candidate == author]
            if len(pids) + len(existing) > 1 or author in quarantined:
                quarantined.add(author)
                for pid in pids + existing:
                    mapping.pop(pid, None)
                    evidence[pid] = dict(status='author_assigned_to_multiple_pids', method='', iteration=0)
                    pending.discard(pid)
            else:
                pid = pids[0]
                mapping[pid] = author
                evidence[pid] = dict(status='matched', method=proposals[pid][1], iteration=proposals[pid][2])
                pending.discard(pid)
    accept(proposals)
    for iteration in range(1, max_rounds+1):
        occupied = set(mapping.values())
        proposals = {}
        for pid in sorted(pending):
            sets = paper_sets(pid, occupied)
            common = set.intersection(*sets) if sets else set()
            named = name_candidates(pid) - occupied - quarantined
            named_common = named & common
            if len(named_common) == 1:
                proposals[pid] = (next(iter(named_common)), 'name_and_work_sets', iteration)
            elif len(common) == 1 and (len(sets) >= 2 or len(sets[0]) == 1):
                proposals[pid] = (next(iter(common)), 'unique_remaining_work_author', iteration)
            elif allow_name_only and not sets:
                exact = name_candidates(pid, True) - occupied - quarantined
                if len(exact) == 1:
                    proposals[pid] = (next(iter(exact)), 'unique_full_name_only', iteration)
        if not proposals:
            break
        accept(proposals)
        print(f'Round {iteration}: proposed {len(proposals):,}; retained {len(mapping):,}', flush=True)
    author_counts = Counter(mapping.values())
    assert all(n == 1 for n in author_counts.values())
    linked = [dict(PID=pid, OpenAlexAuthorID=author, **evidence[pid]) for pid, author in sorted(mapping.items())]
    write_csv(output / 'pid_openalex_crosswalk.csv', linked, ['PID', 'OpenAlexAuthorID', 'status', 'method', 'iteration'])
    unmatched = [dict(PID=pid, **evidence.get(pid, dict(status='ambiguous_or_no_evidence', method='', iteration=0)))
                 for pid in people if pid not in mapping]
    write_csv(output / 'unmatched_people.csv', unmatched, ['PID', 'status', 'method', 'iteration'])
    summary = dict(implementation='orcid_name_worksets',
                   people=len(people), matched=len(mapping), unmatched=len(unmatched),
                   allow_unique_name_only=allow_name_only, max_rounds=max_rounds,
                   methods=dict(Counter(r['method'] for r in linked)), quarantined_authors=len(quarantined))
    (output / 'linkage_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    con.close()
    return mapping


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--aft-root', type=Path, required=True)
    parser.add_argument('--openalex-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-unique-name-only', action='store_true', help='Allow unique normalized-name matches without work evidence')
    parser.add_argument('--max-rounds', type=int, default=6)
    args = parser.parse_args()
    construct_linkage(args.aft_root, args.openalex_root, args.output, args.allow_unique_name_only, args.max_rounds)

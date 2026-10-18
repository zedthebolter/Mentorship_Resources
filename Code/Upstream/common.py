"""Shared normalization and streaming readers for the documented cleaned snapshot."""
from __future__ import annotations
import csv
import gzip
import json
import math
import re
import sqlite3
import unicodedata
from pathlib import Path


def rows(path):
    path = Path(path)
    suffix = path.suffixes[-2] if path.suffix == '.gz' else path.suffix
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t' if suffix == '.tsv' else ',')
        if reader.fieldnames is None:
            raise ValueError(f'No header: {path.name}')
        for row in reader:
            yield {str(k).strip(): str(v or '').strip() for k, v in row.items() if k is not None}


def value(row, *columns):
    for key in columns:
        item = row.get(key, '')
        if str(item).strip() and str(item).lower() not in {'nan', 'none', 'null'}:
            return str(item).strip()
    return ''


def oa_id(item, prefix):
    item = str(item or '').strip().rstrip('/').rsplit('/', 1)[-1]
    return item if re.fullmatch(prefix + r'\d+', item) and item != 'A9999999999' else ''


def integer(item):
    try:
        x = float(item)
        return int(x) if math.isfinite(x) and x.is_integer() else None
    except (ValueError, TypeError):
        return None


def number(item):
    try:
        x = float(item)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def doi(item):
    text = str(item or '').strip().casefold()
    for prefix in ['https://doi.org/', 'http://doi.org/', 'http://dx.doi.org/', 'https://dx.doi.org/', 'doi:']:
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text if re.fullmatch(r'10\.\d{4,9}/\S+', text) else ''


def pmid(item):
    item = str(item or '').strip().rstrip('/').rsplit('/', 1)[-1]
    item = item.removeprefix('pmid:')
    return item if item.isdigit() else ''


def orcid(item):
    item = str(item or '').strip().rstrip('/').rsplit('/', 1)[-1].upper()
    digits = item.replace('-', '')
    if not re.fullmatch(r'\d{15}[\dX]', digits):
        return ''
    total = 0
    for char in digits[:15]:
        total = (total + int(char)) * 2
    result = (12 - total % 11) % 11
    if digits[-1] != ('X' if result == 10 else str(result)):
        return ''
    return '-'.join(digits[i:i+4] for i in range(0, 16, 4))


def name_key(item):
    # Preserve letters/diacritics; punctuation is a separator, not a fuzzy-name match.
    text = unicodedata.normalize('NFKC', str(item or '')).casefold()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in text).split())


def person_name_keys(person):
    first, middle, last = [value(person, k) for k in ['FirstName', 'MiddleName', 'LastName']]
    if not first or not last:
        return set(), set()
    strong = {name_key(' '.join([first, middle, last])), name_key(' '.join([first, last])),
              name_key(' '.join([last, first, middle])), name_key(' '.join([last, first]))}
    weak = {name_key(' '.join([first[:1], middle[:1], last])), name_key(' '.join([first[:1], last])),
            name_key(' '.join([first, middle[:1], last]))}
    return strong - {''}, weak - strong - {''}


def write_csv(path, records, columns=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = list(records)
    if columns is None:
        columns = list(records[0]) if records else []
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in records:
            writer.writerow({k: '' if v is None or isinstance(v, float) and not math.isfinite(v) else v for k, v in row.items()})


def database(path):
    connection = sqlite3.connect(path)
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA synchronous=NORMAL')
    connection.execute('PRAGMA temp_store=FILE')
    return connection


def insert_batches(connection, sql, records, size=20000):
    batch = []
    total = 0
    for row in records:
        batch.append(row)
        if len(batch) >= size:
            connection.executemany(sql, batch)
            connection.commit()
            total += len(batch)
            batch = []
    if batch:
        connection.executemany(sql, batch)
        connection.commit()
        total += len(batch)
    return total


def read_mapping(path):
    mapping = {}
    for row in rows(path):
        pid = value(row, 'PID', 'MenteeID')
        author = oa_id(value(row, 'OpenAlexAuthorID', 'Final_OpenAlexAuthorID', 'author_OpenAlex_id', 'author_id', 'orcid'), 'A')
        if not pid or not author:
            continue
        if pid in mapping and mapping[pid] != author:
            raise ValueError(f'Multiple assignments for PID {pid}')
        mapping[pid] = author
    if not mapping:
        raise ValueError('No valid PID/OpenAlex author assignments found in the crosswalk')
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('One OpenAlex author is assigned to multiple PIDs')
    return mapping


def h_index(counts):
    values = list(counts)
    if any(integer(c) is None or float(c) < 0 for c in values):
        raise ValueError('h-index needs nonnegative integer citation counts; missing is not zero')
    return max([0] + [rank for rank, count in enumerate(sorted(map(int, values), reverse=True), 1) if count >= rank])


def topic_retention(training, later):
    if not training:
        return None
    return len(training & later) / len(training)

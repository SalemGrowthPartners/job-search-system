"""Validated discovery records, conservative identity matching, and CSV projection."""
import copy
import csv
import hashlib
import io
import math
from datetime import date
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from score_job import CONFIG, score_job
import provenance

STATUSES = set('DISCOVERED REVIEW SHORTLISTED PREPARING READY PREPARED APPLIED INTERVIEW REJECTED WITHDRAWN OFFER'.split())
HEADER = 'id,company,role,location,salary_min,salary_max,source,url,date_found,date_posted,qualification_score,career_fit_score,confidence,status,resume_version,notes'.split(',')


def canonical_url(value):
    if not isinstance(value, str):
        raise ValueError('url must be a string')
    p = urlsplit(value.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('url must be an absolute HTTP(S) posting URL without credentials')
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'gclid', 'fbclid'}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', urlencode(sorted(query)), ''))


def number(value, label, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    if value < low or (high is not None and value > high):
        raise ValueError(f'{label} is out of range')


def normalize(raw, tracks):
    if not isinstance(raw, dict):
        raise ValueError('each job must be an object')
    r = copy.deepcopy(raw)
    if type(r.get('schema_version')) is not int or r['schema_version'] not in (1, 2):
        raise ValueError('schema_version must be 1 or 2')
    for key in ('company', 'role', 'source', 'description'):
        if not isinstance(r.get(key), str) or not r[key].strip():
            raise ValueError(f'{key} must be a nonempty string')
        r[key] = r[key].strip()
    r['url'] = canonical_url(r.get('url'))
    for key in ('location', 'requisition_id'):
        if r.get(key) is not None and (not isinstance(r[key], str) or not r[key].strip()):
            raise ValueError(f'{key} must be a nonempty string or null')
        r.setdefault(key, None)
    for key in ('date_found', 'date_posted'):
        value = r.get(key)
        if key == 'date_found' or value is not None:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError(f'{key} must be YYYY-MM-DD')
        r.setdefault(key, None)
    for key in ('salary_min', 'salary_max', 'domestic_trips_per_year'):
        if r.get(key) is not None:
            number(r[key], key)
        r.setdefault(key, None)
    if r['salary_min'] is not None and r['salary_max'] is not None and r['salary_min'] > r['salary_max']:
        raise ValueError('salary_min exceeds salary_max')
    if any(r[k] is not None for k in ('salary_min', 'salary_max')) and r.get('salary_basis') != 'annual_base_usd':
        raise ValueError('known salary requires salary_basis=annual_base_usd; retain unconverted pay in description/unknowns')
    for key in ('mandatory_relocation', 'major_organic_social_ownership'):
        if r.get(key) is not None and type(r[key]) is not bool:
            raise ValueError(f'{key} must be boolean or null')
        r.setdefault(key, None)
    for key, config_key in [('qualification', 'qualification_score'), ('career_fit', 'career_fit_score')]:
        values = r.get(key)
        if not isinstance(values, dict) or set(values) != set(CONFIG[config_key]):
            raise ValueError(f'{key} must contain exactly the configured dimensions')
        for dimension, value in values.items():
            number(value, f'{key}.{dimension}', high=1)
    number(r.get('confidence'), 'confidence', high=1)
    for key in ('strengths', 'gaps', 'unknowns', 'conflicts', 'search_tracks'):
        if not isinstance(r.get(key), list) or any(not isinstance(v, str) or not v.strip() for v in r[key]):
            raise ValueError(f'{key} must be a list of nonempty strings')
    if not r['search_tracks'] or set(r['search_tracks']) - set(tracks):
        raise ValueError('search_tracks must reference configured tracks')
    # IDs, scores, status and provenance are owned by storage, never by import input.
    for key in ('id', 'scores', 'status', 'sources', 'last_seen', 'candidate_group', 'application_date'):
        r.pop(key, None)
    if r['schema_version'] == 2 or 'provenance' in r:
        r['provenance'] = provenance.validate(r.get('provenance'), canonical_url)
        if r['schema_version'] == 2 and r['provenance']['availability'] != 'open':
            raise ValueError('Version 2 import requires verified-open provenance; keep other leads in staging')
        if r['schema_version'] == 2 and r['url'] != r['provenance']['authoritative_posting_url']:
            raise ValueError('url must be the authoritative posting URL for version 2')
    return r


def identities(r):
    urls = {canonical_url(s['url']) for s in r.get('sources', [])} | {canonical_url(r['url'])}
    keys = {('url', u) for u in urls}
    p = r.get('provenance', {})
    if p.get('authoritative_posting_url'):
        keys.add(('url', canonical_url(p['authoritative_posting_url'])))
    if all(p.get(k) for k in ('employer_domain', 'ats_provider', 'ats_board_id', 'ats_posting_id')):
        keys.add(('ats', p['employer_domain'].casefold(), p['ats_provider'].casefold(), p['ats_board_id'], p['ats_posting_id']))
    if r.get('requisition_id'):
        keys.add(('req', r['company'].strip().casefold(), r['requisition_id'].strip().casefold()))
    return keys


def group(scores):
    t = CONFIG['thresholds']
    q, c = scores['qualification_score'], scores['career_fit_score']
    stretch = t['stretch_candidate']
    if scores['hard_reject']:
        return 'rejected'
    if stretch['qualification_min'] <= q <= stretch['qualification_max'] and c >= stretch['career_fit_min']:
        return 'stretch'
    if q >= t['minimum_qualification'] and c >= t['minimum_career_fit']:
        return 'qualified'
    return 'below_threshold'


def merge(records, incoming):
    matches = [r for r in records if identities(r) & identities(incoming)]
    if len(matches) > 1:
        raise ValueError('ambiguous identity bridges multiple saved jobs; reconcile before importing')
    old = matches[0] if matches else None
    r = copy.deepcopy(incoming)
    r['id'] = old['id'] if old else 'job-' + hashlib.sha256(r['url'].encode()).hexdigest()[:20]
    if old or 'provenance' in r:
        r['provenance'] = provenance.combine(old.get('provenance', provenance.legacy()) if old else None, r.get('provenance'))
    if old and r.get('date_posted') is None:
        r['date_posted'] = old.get('date_posted')
    r['description_hash'] = provenance.description_hash(r['description'])
    r['scores'] = score_job(r)
    r['candidate_group'] = group(r['scores'])
    r['status'] = old['status'] if old else ('REJECTED' if r['scores']['hard_reject'] else 'REVIEW' if r['candidate_group'] in ('qualified', 'stretch') else 'DISCOVERED')
    if old and old.get('application_date'):
        r['application_date'] = old['application_date']
    r['sources'] = copy.deepcopy(old.get('sources', [])) if old else []
    source = {'source': r['source'], 'url': r['url']}
    if source not in r['sources']:
        r['sources'].append(source)
    r['last_seen'] = max(incoming['date_found'], old.get('last_seen', old['date_found'])) if old else incoming['date_found']
    r['date_found'] = min(incoming['date_found'], old['date_found']) if old else incoming['date_found']
    if old:
        r['search_tracks'] = sorted(set(r['search_tracks']) | set(old['search_tracks']))
        r['requisition_id'] = r.get('requisition_id') or old.get('requisition_id')
        records[records.index(old)] = r
    else:
        records.append(r)
    return r


def tracker_text(path, records):
    if path.exists():
        with path.open(newline='') as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)
        if not fields or not set(HEADER) <= set(fields):
            raise ValueError('tracker is missing required columns')
    else:
        fields, rows = HEADER[:], []
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('malformed tracker row')
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('duplicate tracker IDs')
    if any(row['status'] not in STATUSES for row in rows):
        raise ValueError('invalid tracker status')
    by_id = {row['id']: row for row in rows}
    for r in records:
        existing = by_id.get(r['id'])
        row = existing if existing is not None else dict.fromkeys(fields, '')
        for key in ('id', 'company', 'role', 'location', 'salary_min', 'salary_max', 'source', 'url', 'date_found', 'date_posted'):
            row[key] = r.get(key) if r.get(key) is not None else ''
        for key in ('qualification_score', 'career_fit_score', 'confidence'):
            row[key] = r['scores'][key]
        if existing is None:
            row['status'] = r['status']
            rows.append(row)
        else:
            r['status'] = row['status']
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def ranked(records):
    return sorted(records, key=lambda r: (r['candidate_group'] not in ('qualified', 'stretch'),
                  r['scores']['hard_reject'], -r['scores']['career_fit_score'],
                  -r['scores']['qualification_score'], -r['scores']['confidence'], r['id']))

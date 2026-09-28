"""Planning, unscored lead staging, and auditable source coverage for AI-led /find."""
import copy
import hashlib
import json
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import yaml
from discovery import canonical_url
import provenance
import recency


def load(root, path, default):
    p = root / path
    return json.loads(p.read_text()) if p.exists() else copy.deepcopy(default)


def configuration(root):
    values = [yaml.safe_load((root / 'config' / name).read_text()) for name in
              ('job-sources.yaml', 'capability-queries.yaml', 'target-companies.yaml')]
    registry, queries, watch = values
    sources = registry['sources']
    ids = [s['id'] for s in sources]
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError('Source IDs must be unique and nonempty')
    if sum(registry['allocation_percent'].values()) != 100:
        raise ValueError('Source allocation must total 100')
    tracks = yaml.safe_load((root/'config/search-tracks.yaml').read_text())['search_tracks']
    for source in sources:
        if source['tier'] not in ('core', 'rotate', 'optional'):
            raise ValueError('Invalid source tier')
        if source.get('url'):
            canonical_url(source['url'])
    if len({q['id'] for q in queries['queries']}) != len(queries['queries']):
        raise ValueError('Duplicate capability query IDs')
    for query in queries['queries']:
        if query['track'] not in tracks or type(query['stretch']) is not bool:
            raise ValueError('Invalid capability query')
    if len({c['id'] for c in watch['companies']}) != len(watch['companies']):
        raise ValueError('Duplicate watch company IDs')
    for company in watch['companies']:
        if company.get('career_url'):
            canonical_url(company['career_url'])
        if company['check_interval_days'] <= 0:
            raise ValueError('Invalid company check interval')
    recency.policy(root)
    return values


def source_ids(root, p):
    allowed = {s['id'] for s in configuration(root)[0]['sources']}
    for o in p.get('observations', []) + ([p['origin']] if p.get('origin') else []):
        if o['source_id'] not in allowed:
            raise ValueError('Unregistered source_id: ' + o['source_id'])


def plan(root, tracks, mode='standard', today=None):
    today = today or date.today()
    registry, capabilities, watch = configuration(root)
    runs = load(root, 'jobs/discovery-runs.json', [])
    completed = [r for r in runs if r['completed']]
    rotation = len(completed)
    titles = []
    for name, track in sorted(tracks.items(), key=lambda item: item[1]['priority']):
        searches = track['searches']
        indexes = range(len(searches)) if mode == 'broad' else [(rotation * 2 + j) % len(searches) for j in range(2 if track['priority'] == 1 else 1)]
        titles += [{'id': name + ':' + str(i), 'track': name, 'priority': track['priority'], 'query': searches[i]} for i in indexes]
    rotating = [s for s in registry['sources'] if s['tier'] == 'rotate']
    count = registry['rotating_sources_per_run']
    chosen = rotating if mode == 'broad' else [rotating[(rotation * count + i) % len(rotating)] for i in range(min(count, len(rotating)))]
    sources = [s for s in registry['sources'] if s['tier'] == 'core'] + chosen
    qs = capabilities['queries']
    selected = qs if mode == 'broad' else [qs[(rotation * 3 + i) % len(qs)] for i in range(min(3,len(qs)))]
    if not any(q['stretch'] for q in selected):
        selected.append(next(q for q in qs if q['stretch']))
    due = []
    for company in watch['companies']:
        if not company['enabled']:
            continue
        checks = [c['at'] for run in runs for c in run.get('company_checks', []) if c['company_id'] == company['id'] and c['result'] == 'checked']
        if company.get('last_successful_check'):
            checks.append(company['last_successful_check'])
        last = max(checks) if checks else None
        next_due = (date.fromisoformat(last[:10]) + timedelta(days=company['check_interval_days'])).isoformat() if last else None
        if mode == 'broad' or next_due is None or next_due <= today.isoformat():
            due.append(dict(company, last_successful_check=last, next_check_due=next_due))
    since = max((r['finished_at'] for r in completed), default=None)
    return {'mode':mode, 'since':since, 'freshness_search':recency.search_plan(root, since, mode, today),
            'retry_coverage':[e for r in runs[-1:] for e in r['coverage'] if e['result'] in ('blocked','skipped')],
            'existing_jobs':[{'id':r['id'], 'company':r['company'], 'role':r['role'], 'status':r['status'], 'url':r['url'], 'last_verified_at':r.get('provenance',{}).get('last_verified_at'), 'description_hash':r.get('description_hash')} for r in load(root,'jobs/discovered/records.json',[])], 'rotation':rotation, 'title_queries':titles,
            'capability_queries':selected, 'sources':sources, 'due_companies':due,
            'optional_sources':[s for s in registry['sources'] if s['tier']=='optional'],
            'allocation_percent':registry['allocation_percent'], 'stretch_exploration_percent':registry['stretch_exploration_percent'],
            'review_display_limit':registry['review_display_limit'],
            'notes':['Broad retains all 33 configured title queries. Standard rotates while covering every track.',
                     'Use since for discovery, not to infer closure or drop older verified-open jobs.',
                     'No network requests or subscriptions are performed by this plan.']}


def stage(root, path, dry_run=False):
    from find_jobs import atomic_write
    raw = json.loads(path.read_text())
    if not isinstance(raw, list) or not raw:
        raise ValueError('Stage input must be a nonempty array')
    validated = []
    for item in raw:
        item = copy.deepcopy(item)
        for key in ('company','role','reason'):
            item[key] = provenance.text(item.get(key),key)
        item['url'] = canonical_url(item.get('url'))
        if item.get('disposition') not in ('pending','screened_out','duplicate'):
            raise ValueError('Lead disposition must be pending, screened_out or duplicate')
        item['provenance'] = provenance.validate(item.get('provenance'),canonical_url)
        if not item['provenance']['origin']:
            raise ValueError('New staged leads require original discovery evidence')
        source_ids(root,item['provenance'])
        item['lead_id'] = 'lead-' + hashlib.sha256(item['url'].encode()).hexdigest()[:20]
        validated.append(item)
    leads = load(root,'jobs/staging/leads.json',[])
    for item in validated:
        old = next((l for l in leads if l['lead_id']==item['lead_id']),None)
        if old:
            item['provenance'] = provenance.combine(old['provenance'],item['provenance'])
            if old.get('promoted_job_id'):
                item['promoted_job_id'] = old['promoted_job_id']
                item['disposition'] = 'promoted'
            leads[leads.index(old)] = item
        else:
            leads.append(item)
    if not dry_run:
        atomic_write(root/'jobs/staging/leads.json',json.dumps(leads,indent=2)+'\n')
    return leads


def promotion(root, path):
    """Attach immutable first discovery and staged observations to scored analyses."""
    jobs = json.loads(path.read_text())
    if not isinstance(jobs,list) or not jobs:
        raise ValueError('Promotion requires a nonempty analysis array')
    leads = load(root,'jobs/staging/leads.json',[])
    for job in jobs:
        lead = next((l for l in leads if l['lead_id']==job.get('lead_id')),None)
        if not lead or lead['disposition'] not in ('pending','promoted'):
            raise ValueError('Promotion requires a pending or previously promoted lead_id')
        if job.get('schema_version') != 2:
            raise ValueError('Promotion requires schema_version 2')
        # Explicit lead_id is the agent-reviewed identity link, never title matching.
        if job.get('company','').strip().casefold() != lead['company'].strip().casefold():
            raise ValueError('Company mismatch between lead and analysis')
        p = provenance.validate(job.get('provenance'),canonical_url)
        if p['availability'] != 'open':
            raise ValueError('Only verified-open leads may be promoted')
        job['provenance'] = provenance.combine(lead['provenance'],p)
    return jobs, leads


def record_run(root, path, dry_run=False):
    from find_jobs import atomic_write
    run=json.loads(path.read_text())
    if not isinstance(run,dict) or not re.fullmatch(r'[A-Za-z0-9_-]+',run.get('run_id','')):
        raise ValueError('run_id must be a safe nonempty identifier')
    if run.get('mode') not in ('standard','broad') or type(run.get('completed')) is not bool:
        raise ValueError('Run requires mode and completed boolean')
    for key in ('started_at','finished_at'):
        run[key]=provenance.timestamp(run.get(key))
    if run['finished_at'] < run['started_at']:
        raise ValueError('Run ends before it starts')
    registry,_,watch=configuration(root)
    allowed={s['id'] for s in registry['sources']}
    events=run.get('coverage')
    if not isinstance(events,list) or not events:
        raise ValueError('Run must include coverage events, including skips/blocks')
    for e in events:
        if e.get('source_id') not in allowed or e.get('result') not in ('checked','blocked','skipped'):
            raise ValueError('Invalid coverage source/result')
        for key in ('query_id','reason'):
            provenance.text(e.get(key),key)
        if 'date_filter' in e:
            provenance.text(e['date_filter'], 'date_filter')
        if 'date_filter_supported' in e and type(e['date_filter_supported']) is not bool:
            raise ValueError('date_filter_supported must be boolean')
        minutes=e.get('minutes',0)
        if type(minutes) not in (int,float) or minutes<0 or not __import__('math').isfinite(minutes):
            raise ValueError('Invalid elapsed minutes')
    for c in run.get('company_checks',[]):
        if c.get('company_id') not in {x['id'] for x in watch['companies']} or c.get('result') not in ('checked','blocked','skipped'):
            raise ValueError('Invalid company check')
        c['at']=provenance.timestamp(c.get('at'))
        provenance.text(c.get('evidence'), 'company check evidence')
    runs=load(root,'jobs/discovery-runs.json',[])
    old=next((r for r in runs if r['run_id']==run['run_id']),None)
    if old:
        if old != run: raise ValueError('Run IDs are immutable; use a new run ID for a new attempt')
    else: runs.append(run)
    if not dry_run: atomic_write(root/'jobs/discovery-runs.json',json.dumps(runs,indent=2)+'\n')
    return run


def report(root):
    registry,_,_=configuration(root)
    runs=load(root,'jobs/discovery-runs.json',[])
    leads=load(root,'jobs/staging/leads.json',[])
    records=load(root,'jobs/discovered/records.json',[])
    import csv
    statuses={}
    if (root/'tracker.csv').exists():
        with (root/'tracker.csv').open(newline='') as f:
            statuses={r['id']:r['status'] for r in csv.DictReader(f)}
    results=[]
    for source in registry['sources']:
        sid=source['id']
        sightings={l['lead_id'] for l in leads if any(o['source_id']==sid for o in l['provenance']['observations'])}
        originated=[r for r in records if (r.get('provenance',{}).get('origin') or {}).get('source_id')==sid]
        events=[e for run in runs for e in run['coverage'] if e['source_id']==sid]
        shortlist=sum(statuses.get(r['id'],r['status']) in ('SHORTLISTED','PREPARING','PREPARED','READY','APPLIED','INTERVIEW','OFFER') for r in originated)
        results.append({'source_id':sid,'unique_leads_seen':len(sightings),'originated_verified_records':len(originated),
            'shortlisted_or_later':shortlist,'shortlist_rate':shortlist/len(originated) if originated else None,
            'duplicate_leads':sum(l['lead_id'] in sightings and l['disposition']=='duplicate' for l in leads),
            'closed_leads':sum(l['lead_id'] in sightings and l['provenance']['availability']=='closed' for l in leads),
            'access_failures':sum(e['result']=='blocked' for e in events),'minutes':sum(e.get('minutes',0) for e in events)})
    return {'runs':runs,'sources':results,'pending_leads':sum(l['disposition']=='pending' for l in leads),
            'legacy_origin_unknown':sum(not r.get('provenance',{}).get('origin') for r in records),
            'note':'Observed local yield, not total market coverage. Zero observations do not imply source quality. Shortlist rate is current-state based.'}

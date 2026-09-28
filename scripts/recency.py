"""Read-only application urgency. Never modifies qualification or career-fit scores."""
from datetime import date, datetime, timedelta
import csv
import json
from zoneinfo import ZoneInfo
import yaml


def policy(root):
    p=yaml.safe_load((root/'config/recency.yaml').read_text())
    if p.get('schema_version') != 1:
        raise ValueError('Unsupported recency policy version')
    if len(p['bands']) != 4 or len({b['label'] for b in p['bands']}) != 4:
        raise ValueError('Configure four distinct urgency bands')
    ages=[b['max_age_days'] for b in p['bands']]
    if any(type(x) is not int or x<0 for x in ages) or ages!=sorted(set(ages)):
        raise ValueError('Recency bands require ascending unique nonnegative days')
    if not 0<=p['exceptional_fit_min']<=100:
        raise ValueError('Invalid exceptional fit threshold')
    for key in ('reverify_after_days','verification_max_age_days','evergreen_check_after_days'):
        if type(p[key]) is not int or p[key]<0:raise ValueError('Invalid recency day threshold')
    if p['evergreen_check_after_days']<p['reverify_after_days']:raise ValueError('Evergreen threshold precedes verification threshold')
    if not p['search_windows_days'] or any(type(x) is not int or x<1 for x in p['search_windows_days']):raise ValueError('Invalid search windows')
    for mode in ('standard','broad'):
        if not 0<=p['undated_search_effort_percent'][mode]<=100:raise ValueError('Invalid undated allocation')
    return p


def local_today():
    return datetime.now(ZoneInfo('America/Los_Angeles')).date()


def calendar_day(value):
    # Date-only values stay dates; timestamps use the user's configured timezone for age.
    if len(value)==10:return date.fromisoformat(value)
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).date()


def search_plan(root, since, mode, today=None):
    today=today or local_today();p=policy(root)
    windows=[{'label':f'last_{days}_days','from_date':(today-timedelta(days=days)).isoformat(),'through_date':today.isoformat()} for days in p['search_windows_days']]
    if since and calendar_day(since)<calendar_day(windows[-1]['from_date']):
        windows.append({'label':'since_last_completed_run','from_date':calendar_day(since).isoformat(),'through_date':today.isoformat()})
    return {'windows':windows,'sort':'newest where supported','undated_search_effort_percent':p['undated_search_effort_percent'][mode],
            'instructions':['Use source date filters only when available; record actual filter and raw date meaning.',
                            'Overlap 3/7-day passes; deduplicate before scoring. Indexing/update dates do not prove original publication.',
                            'Include an undated sweep for exceptional older matches and sources without filters; broad allocates more effort.',
                            'Revisit blocked checks outside the cutoff; do not surface unchanged older inventory as new.']}


def assess(record, p, today=None):
    today=today or local_today();v=record.get('provenance',{})
    original=v.get('original_posted_at')
    age=(today-calendar_day(original)).days if original else None
    reasons=[];blockers=[]
    if age is not None and age<0:
        blockers.append('Original posting date is in the future; resolve date evidence')
        age=None
    if age is None:
        band='unknown';order=2;reasons.append('Original posting date unknown: no freshness bonus or assumed-age penalty')
    else:
        match=next(((i,b) for i,b in enumerate(p['bands']) if age<=b['max_age_days']),None)
        order,band=(match[0],match[1]['label']) if match else (len(p['bands']),'older')
        reasons.append(f'Originally posted {age} days ago; {band} urgency')
    exceptional=record['scores']['career_fit_score']>=p['exceptional_fit_min'] and record['candidate_group'] in ('qualified','stretch')
    if exceptional and age is not None and age>p['bands'][1]['max_age_days']:
        order=min(order,1);reasons.append('Exceptional fit—worth pursuing despite age')
    verified=v.get('last_verified_at')
    verification_age=(today-calendar_day(verified)).days if verified else None
    if v.get('availability')!='open':blockers.append('Current employer/application availability needs verification')
    if verification_age is not None and verification_age<0:blockers.append('Verification timestamp is in the future')
    if age is not None and age>p['reverify_after_days']:
        if verification_age is None or verification_age>p['verification_max_age_days']:
            blockers.append('Older posting requires a fresh employer/application check')
    if age is not None and age>p['evergreen_check_after_days']:
        check=v.get('evergreen_checked_at')
        checked_age=(today-calendar_day(check)).days if check else None
        if checked_age is None or checked_age<0 or checked_age>p['verification_max_age_days'] or not v.get('evergreen_check_evidence'):
            blockers.append('Substantially older posting requires an evergreen/talent-pool check')
    if record.get('conflicts'):blockers.append('Resolve recorded conflicts before recommending application')
    return {'original_posted_at':original,'first_discovered_at':(v.get('origin') or {}).get('at'),
            'last_verified_at':verified,'age_days':age,'recency_band':band,'exceptional_fit':exceptional,
            'priority_order':order,'reasons':reasons,'verification_needed':blockers}


def queue(root, today=None):
    from discovery import ranked
    if (root/'jobs/.discovery-transaction.json').exists():
        raise ValueError('Recover pending transaction before reading application priority')
    p=policy(root);path=root/'jobs/discovered/records.json'
    records=json.loads(path.read_text()) if path.exists() else []
    statuses={}
    if (root/'tracker.csv').exists():
        with (root/'tracker.csv').open(newline='') as f:statuses={r['id']:r['status'] for r in csv.DictReader(f)}
    active=[];excluded=[];verify=[]
    for r in records:
        status=statuses.get(r['id'],r['status'])
        if status in ('APPLIED','INTERVIEW','REJECTED','WITHDRAWN','OFFER') or r['candidate_group'] not in ('qualified','stretch') or r['scores']['hard_reject']:
            excluded.append(r['id']);continue
        assessment=assess(r,p,today)
        item={'id':r['id'],'company':r['company'],'role':r['role'],'status':status,'scores':r['scores'],
              'candidate_group':r['candidate_group'],'application_url':r.get('provenance',{}).get('application_url'),**assessment}
        (verify if assessment['verification_needed'] else active).append(item)
    active.sort(key=lambda x:(x['priority_order'],-x['scores']['career_fit_score'],-x['scores']['qualification_score'],-x['scores']['confidence'],x['id']))
    included={i['id'] for i in active+verify}
    return {'as_of':(today or local_today()).isoformat(),'application_priority':active,'needs_verification':verify,
            'fit_order':[r['id'] for r in ranked(records) if r['id'] in included],
            'exceptional_older_matches':[i for i in active+verify if i['exceptional_fit'] and i['age_days'] is not None and i['age_days']>p['bands'][1]['max_age_days']],
            'unknown_date_matches':[i for i in active+verify if i['age_days'] is None],
            'excluded_ids':excluded,'note':'Urgency is separate from unchanged fit/qualification scores. Highlights include verification blockers; they are not application clearance.'}

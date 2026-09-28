#!/usr/bin/env python3
"""Local helpers for the conversational /onboard workflow.

The assistant performs document reading and the interview. This helper inventories
source files, maintains an auditable evidence ledger, and validates readiness.
It never promotes an inferred claim to confirmed status.
"""
import argparse, hashlib, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / 'onboarding' / 'source-documents'
LEDGER = ROOT / 'onboarding' / 'claim-review.yaml'
ALLOWED = {'proposed', 'resume_supported', 'confirmed', 'disputed', 'rejected'}


def load_yaml(path):
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def save_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def intake(paths, kind):
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    inventory_path = ROOT / 'onboarding' / 'source-inventory.json'
    inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else []
    by_hash = {x['sha256']: x for x in inventory}
    added=[]
    for raw in paths:
        src=Path(raw).expanduser().resolve()
        if not src.is_file(): raise ValueError(f'File not found: {src}')
        digest=hashlib.sha256(src.read_bytes()).hexdigest()
        if digest in by_hash:
            added.append(dict(by_hash[digest], duplicate=True)); continue
        safe=f'{kind}-{len(inventory)+1:02d}{src.suffix.lower()}'
        dst=SOURCE_DIR/safe
        shutil.copy2(src,dst)
        item={'id':safe.rsplit('.',1)[0], 'kind':kind, 'stored_name':safe,
              'original_name':src.name, 'sha256':digest,
              'added_at':datetime.now(timezone.utc).isoformat()}
        inventory.append(item); by_hash[digest]=item; added.append(item)
    inventory_path.write_text(json.dumps(inventory,indent=2)+'\n')
    return added


def validate_ledger():
    data=load_yaml(LEDGER) or {'schema_version':1,'claims':[],'conflicts':[]}
    if data.get('schema_version') != 1: raise ValueError('Unsupported claim-review schema')
    ids=set()
    for c in data.get('claims',[]):
        if not c.get('id') or c['id'] in ids: raise ValueError('Claim IDs must be unique and nonempty')
        ids.add(c['id'])
        if c.get('status') not in ALLOWED: raise ValueError(f"Invalid claim status: {c.get('status')}")
        if c['status']=='confirmed' and not c.get('user_confirmation'):
            raise ValueError(f"Confirmed claim {c['id']} requires recorded user confirmation")
        if c['status']=='resume_supported' and not c.get('source_refs'):
            raise ValueError(f"Resume-supported claim {c['id']} requires source references")
    return data


def status():
    inv=ROOT/'onboarding/source-inventory.json'
    inventory=json.loads(inv.read_text()) if inv.exists() else []
    ledger=validate_ledger()
    prefs=load_yaml(ROOT/'profile/preferences.yaml')
    profile=load_yaml(ROOT/'profile/master-profile.yaml')
    unresolved=[c['id'] for c in ledger.get('claims',[]) if c.get('status') in {'proposed','disputed'}]
    conflicts=[c for c in ledger.get('conflicts',[]) if not c.get('resolved')]
    return {'source_documents':len(inventory),'claims':len(ledger.get('claims',[])),
            'unresolved_claims':unresolved,'unresolved_conflicts':len(conflicts),
            'profile_status':profile.get('onboarding_status'),'preferences_status':prefs.get('onboarding_status'),
            'ready_to_finalize':bool(inventory) and not unresolved and not conflicts}


def finalize():
    s=status()
    if not s['source_documents']: raise ValueError('Add at least one resume/CV before finalizing')
    if s['unresolved_claims'] or s['unresolved_conflicts']:
        raise ValueError('Resolve proposed/disputed claims and conflicts before finalizing')
    required=[ROOT/'profile/master-profile.yaml',ROOT/'profile/accomplishments.yaml',ROOT/'profile/preferences.yaml',ROOT/'config/search-tracks.yaml',ROOT/'config/scoring.yaml',ROOT/'config/capability-queries.yaml',ROOT/'config/target-companies.yaml']
    for p in required:
        data=load_yaml(p)
        if data.get('onboarding_status')!='complete': raise ValueError(f'{p.relative_to(ROOT)} is not marked complete')
        if 'REPLACE WITH' in p.read_text(): raise ValueError(f'{p.relative_to(ROOT)} still contains onboarding placeholders')
    return {'ready':True,'next_commands':['/find','/find broad','/prepare [job/company]','/apply [job/company]','/status']}


def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='cmd',required=True)
    for name,kind in [('add-resume','resume'),('add-writing-sample','writing_sample')]:
        p=sub.add_parser(name); p.add_argument('files',nargs='+'); p.set_defaults(kind=kind)
    sub.add_parser('status'); sub.add_parser('finalize')
    args=ap.parse_args()
    try:
        if args.cmd.startswith('add-'): result=intake(args.files,args.kind)
        elif args.cmd=='status': result=status()
        else: result=finalize()
        print(json.dumps(result,indent=2)); return 0
    except (ValueError,OSError,yaml.YAMLError,json.JSONDecodeError) as e:
        print(f'Onboarding failed: {e}',file=sys.stderr); return 1
if __name__=='__main__': sys.exit(main())

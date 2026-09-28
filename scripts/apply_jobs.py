#!/usr/bin/env python3
"""Local /apply preflight and human-confirmed tracking. Never controls or submits a form."""
import argparse
import csv
from datetime import date
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from find_jobs import atomic_write, apply_transaction
from discovery import HEADER

ROOT = Path(__file__).resolve().parents[1]
ELIGIBLE = {'READY', 'PREPARED'}


def tracker(root, job_id):
    with (root / 'tracker.csv').open(newline='') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    if not fields or not set(HEADER) <= set(fields):
        raise ValueError('Invalid tracker columns')
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('Malformed tracker row')
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate tracker IDs')
    matches = [row for row in rows if row['id'] == job_id]
    if len(matches) != 1:
        raise ValueError('Use an exact existing job ID')
    return fields, rows, matches[0]


def plan(root, job_id, package):
    if (root / 'jobs/.discovery-transaction.json').exists():
        raise ValueError('Pending storage transaction; recover before starting /apply')
    _, _, row = tracker(root, job_id)
    if row['status'] not in ELIGIBLE:
        raise ValueError('Job must be READY or PREPARED; do not infer readiness from files alone')
    package = (root / package).resolve()
    if not package.is_relative_to((root / 'applications').resolve()):
        raise ValueError('Package must be inside applications/')
    manifest = json.loads((package / 'apply-manifest.json').read_text())
    if manifest.get('schema_version') != 1 or manifest.get('job_id') != job_id:
        raise ValueError('Manifest version/job ID mismatch')
    url = manifest.get('application_url', '')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Application URL must be HTTPS without credentials')
    documents = manifest.get('documents')
    if not isinstance(documents, list) or not documents:
        raise ValueError('Manifest needs prepared documents')
    if sum(d.get('kind') == 'resume' for d in documents) != 1:
        raise ValueError('Select exactly one prepared resume')
    selected = []
    for doc in documents:
        path = (package / doc['path']).resolve()
        if not path.is_relative_to(package) or not path.is_file():
            raise ValueError('Document missing or outside package')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != doc.get('sha256'):
            raise ValueError('Prepared document changed; review and refresh manifest')
        selected.append({'kind': doc['kind'], 'path': str(path), 'sha256': digest})
    return {'job': row, 'application_url': url, 'package': str(package),
            'documents': selected, 'profile': {str(p.relative_to(root)): p.read_text()
            for p in sorted((root / 'profile').glob('*.yaml'))},
            'workflow': str(root / 'templates/apply/WORKFLOW.md'),
            'submission_allowed': False}


def confirm(root, job_id, submitted_on, confirmation, dry_run=False):
    # This records a human report. It is not authorization to click Submit.
    if not confirmation or not confirmation.strip():
        raise ValueError('Explicit user submission confirmation is required')
    if date.fromisoformat(submitted_on).isoformat() != submitted_on or date.fromisoformat(submitted_on) > date.today():
        raise ValueError('Use an actual application date in YYYY-MM-DD, not a future date')
    journal = root / 'jobs/.discovery-transaction.json'
    if journal.exists():
        raise ValueError('Pending transaction; use recover before making further changes')
    fields, rows, row = tracker(root, job_id)
    if row['status'] == 'APPLIED':
        if row.get('application_date') == submitted_on:
            return {'status': 'APPLIED', 'changed': False}
        raise ValueError('Already applied with a different date; resolve rather than overwrite')
    if row['status'] not in ELIGIBLE:
        raise ValueError('Only READY/PREPARED jobs can be confirmed applied')
    if 'application_date' not in fields:
        fields.append('application_date')
    row['status'] = 'APPLIED'
    row['application_date'] = submitted_on
    row['notes'] = (row['notes'] + '\n' if row['notes'] else '') + 'User confirmed submission: ' + confirmation.strip()
    records = json.loads((root / 'jobs/discovered/records.json').read_text())
    matches = [r for r in records if r['id'] == job_id]
    if len(matches) != 1:
        raise ValueError('Expected one matching normalized job record')
    matches[0]['status'] = 'APPLIED'
    matches[0]['application_date'] = submitted_on
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    if not dry_run:
        payload = {'records': records, 'tracker': output.getvalue()}
        atomic_write(journal, json.dumps(payload, indent=2) + '\n')
        apply_transaction(root, payload)
        journal.unlink()
    return {'status': 'APPLIED', 'application_date': submitted_on, 'changed': not dry_run, 'dry_run': dry_run}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan'); p.add_argument('job_id'); p.add_argument('package', type=Path)
    p = sub.add_parser('confirm-submitted'); p.add_argument('job_id')
    p.add_argument('--date', required=True); p.add_argument('--confirmation', required=True)
    p.add_argument('--dry-run', action='store_true')
    sub.add_parser('recover', help='replay an interrupted local storage transaction; no browser actions')
    args = parser.parse_args()
    fd = os.open(ROOT, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if args.command == 'plan': result = plan(ROOT, args.job_id, args.package)
        elif args.command == 'confirm-submitted':
            result = confirm(ROOT, args.job_id, args.date, args.confirmation, args.dry_run)
        else:
            journal = ROOT / 'jobs/.discovery-transaction.json'
            if journal.exists():
                apply_transaction(ROOT, json.loads(journal.read_text())); journal.unlink()
            result = {'recovered': True}
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Apply failed: {exc}', file=sys.stderr); return 1
    finally:
        os.close(fd)
    return 0


if __name__ == '__main__':
    sys.exit(main())

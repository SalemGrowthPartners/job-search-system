#!/usr/bin/env python3
"""Prepare AI-led search context or ingest analyzed postings; no submission actions."""
import argparse
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import yaml

from discovery import normalize, merge, ranked, tracker_text, identities
from score_job import ROOT
import sourcing
import recency


def context(root, mode="standard"):
    result = {}
    for directory in ('profile', 'config'):
        result[directory] = {str(p.relative_to(root)): p.read_text()
                             for p in sorted((root / directory).glob('*')) if p.is_file()}
    tracks = yaml.safe_load((root / 'config/search-tracks.yaml').read_text())['search_tracks']
    result['search_plan'] = [{'track': name, 'priority': track['priority'], 'query': query}
                             for name, track in sorted(tracks.items(), key=lambda item: item[1]['priority'])
                             for query in track['searches']]
    if (root / "config/job-sources.yaml").exists():
        result["sourcing_plan"] = sourcing.plan(root, tracks, mode)
    return result, tracks


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_transaction(root, payload):
    atomic_write(root / 'jobs/discovered/records.json', json.dumps(payload['records'], indent=2) + '\n')
    atomic_write(root / 'tracker.csv', payload['tracker'])
    if 'leads' in payload:
        atomic_write(root / 'jobs/staging/leads.json', json.dumps(payload['leads'], indent=2) + '\n')


def ingest(root, path, dry_run=False, promote=False):
    _, tracks = context(root)
    if promote:
        raw, leads = sourcing.promotion(root, path)
    else:
        raw = json.loads(path.read_text())
    if not isinstance(raw, list) or not raw:
        raise ValueError('import must be a nonempty JSON array')
    incoming = [normalize(r, tracks) for r in raw]  # Validate the entire batch before writing.
    for r in incoming:
        if r['schema_version'] == 2:
            sourcing.source_ids(root, r['provenance'])
    journal = root / 'jobs/.discovery-transaction.json'
    if journal.exists():
        if dry_run:
            raise ValueError('interrupted transaction pending; run an import to recover first')
        apply_transaction(root, json.loads(journal.read_text()))
        journal.unlink()
        if promote:
            raw, leads = sourcing.promotion(root, path)
            incoming = [normalize(r, tracks) for r in raw]
    saved = root / 'jobs/discovered/records.json'
    records = json.loads(saved.read_text()) if saved.exists() else []
    for r in incoming:
        if r['schema_version'] == 2 and not r['provenance'].get('origin') and not any(identities(old) & identities(r) for old in records):
            raise ValueError('New version 2 discoveries require original discovery provenance')
        saved_record = merge(records, r)
        if promote:
            lead = next(l for l in leads if l['lead_id'] == r['lead_id'])
            lead['disposition'] = 'promoted'
            lead['promoted_job_id'] = saved_record['id']
    tracker = tracker_text(root / 'tracker.csv', records)
    if not dry_run:
        payload = {'records': records, 'tracker': tracker}
        if promote:
            payload['leads'] = leads
        atomic_write(journal, json.dumps(payload, indent=2) + '\n')
        apply_transaction(root, payload)
        journal.unlink()
    return ranked(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    planning = sub.add_parser('plan', help='emit context and repeatable sourcing plan')
    planning.add_argument('--mode', choices=['standard', 'broad'], default='standard')
    for name in ('stage', 'promote', 'log-run'):
        cmd = sub.add_parser(name)
        cmd.add_argument('path', type=Path)
        cmd.add_argument('--dry-run', action='store_true')
    priority = sub.add_parser('priority', help='read-only application urgency, independent of fit scores')
    priority.add_argument('--as-of', type=date.fromisoformat)
    sub.add_parser('report', help='source coverage and measured local yield')
    command = sub.add_parser('import', help='validate, deduplicate, score, rank, and save analyzed postings')
    command.add_argument('path', type=Path)
    command.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            result, _ = context(ROOT, args.mode)
        elif args.command == "priority":
            result = recency.queue(ROOT, args.as_of)
        elif args.command == "report":
            result = sourcing.report(ROOT)
        else:
            # Lock the project directory without creating files, including on dry runs.
            fd = os.open(ROOT, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                if args.command in ('stage', 'log-run') and (ROOT/'jobs/.discovery-transaction.json').exists():
                    raise ValueError('Pending transaction; recover before updating staging or run logs')
                if args.command == 'stage':
                    result = sourcing.stage(ROOT, args.path, args.dry_run)
                elif args.command == 'log-run':
                    result = sourcing.record_run(ROOT, args.path, args.dry_run)
                else:
                    result = ingest(ROOT, args.path, args.dry_run, promote=args.command == 'promote')
            finally:
                os.close(fd)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Discovery failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

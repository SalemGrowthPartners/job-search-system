import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import apply_jobs
from discovery import HEADER, tracker_text, normalize, merge
from find_jobs import context
from find_jobs import apply_transaction


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / 'applications/test'
        self.package.mkdir(parents=True)
        (self.root / 'profile').mkdir()
        (self.root / 'profile/master-profile.yaml').write_text('person:\n  name: Test Person\n')
        (self.root / 'jobs/discovered').mkdir(parents=True)
        self.row = dict.fromkeys(HEADER, '')
        self.row.update(id='job-test', company='Test', role='Role', status='READY', notes='Existing note')
        self.other = dict(self.row, id='job-other', status='REJECTED')
        self.write_tracker()
        self.records = [dict(self.row, scores={'qualification_score': 80, 'career_fit_score': 90, 'confidence': 70}), dict(self.other, scores={'qualification_score': 80, 'career_fit_score': 90, 'confidence': 70})]
        (self.root / 'jobs/discovered/records.json').write_text(json.dumps(self.records))
        (self.package / 'resume.pdf').write_bytes(b'fixture resume')
        self.manifest = {'schema_version': 1, 'job_id': 'job-test', 'application_url': 'https://example.com/apply', 'documents': [{'kind': 'resume', 'path': 'resume.pdf', 'sha256': hashlib.sha256(b'fixture resume').hexdigest()}]}
        self.save_manifest()
        self.today = date.today().isoformat()

    def write_tracker(self):
        with (self.root / 'tracker.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=HEADER + ['custom'])
            w.writeheader(); w.writerows([dict(self.row, custom='retain'), self.other])

    def save_manifest(self):
        (self.package / 'apply-manifest.json').write_text(json.dumps(self.manifest))

    def plan(self):
        return apply_jobs.plan(self.root, 'job-test', self.package)

    def confirm(self, **kw):
        return apply_jobs.confirm(self.root, 'job-test', kw.pop('submitted_on', self.today), kw.pop('confirmation', 'I submitted today.'), **kw)

    def snapshot(self):
        return {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_plan_is_read_only_and_never_allows_submit(self):
        before = self.snapshot()
        self.assertFalse(self.plan()['submission_allowed'])
        self.assertEqual(before, self.snapshot())

    def test_readiness(self):
        for status in ['SHORTLISTED', 'PREPARING', 'APPLIED', 'REJECTED']:
            self.row['status'] = status; self.write_tracker()
            with self.assertRaises(ValueError): self.plan()
        self.row['status'] = 'PREPARED'; self.write_tracker()
        self.plan()

    def test_document_hash_and_traversal(self):
        (self.package / 'resume.pdf').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.plan()
        self.manifest['documents'][0]['path'] = '../../tracker.csv'; self.save_manifest()
        with self.assertRaises(ValueError): self.plan()

    def test_wrong_job_and_url(self):
        self.manifest['job_id'] = 'wrong'; self.save_manifest()
        with self.assertRaises(ValueError): self.plan()
        self.manifest['job_id'] = 'job-test'; self.manifest['application_url'] = 'javascript:alert(1)'; self.save_manifest()
        with self.assertRaises(ValueError): self.plan()

    def test_confirmation_and_date_required(self):
        before = self.snapshot()
        for kwargs in [{'confirmation': ''}, {'submitted_on': 'nonsense'}, {'submitted_on': (date.today()+timedelta(days=1)).isoformat()}]:
            with self.assertRaises(ValueError): self.confirm(**kwargs)
        self.assertEqual(before, self.snapshot())

    def test_dry_run_and_idempotent_confirmation(self):
        before = self.snapshot(); self.confirm(dry_run=True)
        self.assertEqual(before, self.snapshot())
        self.confirm()
        _, rows, row = apply_jobs.tracker(self.root, 'job-test')
        self.assertEqual(row['status'], 'APPLIED')
        self.assertEqual(row['application_date'], self.today)
        self.assertEqual(row['custom'], 'retain')
        self.assertIn('Existing note', row['notes'])
        self.assertEqual(rows[1]['status'], 'REJECTED')
        records = json.loads((self.root/'jobs/discovered/records.json').read_text())
        self.assertEqual(records[0]['application_date'], self.today)
        self.assertEqual(records[0]['status'], 'APPLIED')
        before = self.snapshot(); self.assertFalse(self.confirm()['changed'])
        self.assertEqual(before, self.snapshot())
        with self.assertRaises(ValueError): self.confirm(submitted_on='2020-01-01')
        # The existing discovery projection preserves date, status and custom columns.
        projected = tracker_text(self.root/'tracker.csv', records)
        self.assertIn(self.today, projected)
        self.assertEqual(records[0]['status'], 'APPLIED')

    def test_reimport_preserves_date_and_rejects_imported_date(self):
        project = Path(__file__).resolve().parents[1]
        _, tracks = context(project)
        raw = json.loads((project/'scripts/example-discovery.json').read_text())[0]
        raw['application_date'] = '2020-01-01'
        incoming = normalize(raw, tracks)
        self.assertNotIn('application_date', incoming)
        records = []
        saved = merge(records, incoming)
        saved['status'] = 'APPLIED'; saved['application_date'] = self.today
        refreshed = merge(records, normalize(raw, tracks))
        self.assertEqual(refreshed['application_date'], self.today)
        self.assertEqual(refreshed['status'], 'APPLIED')

    def test_interrupted_transaction_is_recoverable(self):
        with patch('apply_jobs.apply_transaction', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError): self.confirm()
        with self.assertRaises(ValueError): self.plan()
        journal = self.root/'jobs/.discovery-transaction.json'
        apply_transaction(self.root, json.loads(journal.read_text())); journal.unlink()
        self.assertEqual(apply_jobs.tracker(self.root, 'job-test')[2]['status'], 'APPLIED')

    def test_missing_record_does_not_mutate(self):
        (self.root/'jobs/discovered/records.json').write_text('[]')
        before=self.snapshot()
        with self.assertRaises(ValueError): self.confirm()
        self.assertEqual(before,self.snapshot())


if __name__ == '__main__': unittest.main()

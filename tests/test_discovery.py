import copy
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from discovery import HEADER, canonical_url, normalize
from find_jobs import ROOT, context, ingest
from score_job import score_job
import score_job as score_module


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('profile', 'config'):
            shutil.copytree(ROOT / folder, self.root / folder)
        (self.root / 'tracker.csv').write_text(','.join(HEADER) + '\n')
        self.job = json.loads((ROOT / 'scripts/example-discovery.json').read_text())[0]
        self.path = self.root / 'batch.json'
        self.tracks = context(self.root)[1]

    def run_import(self, jobs=None, dry=False):
        self.path.write_text(json.dumps(jobs if jobs is not None else [self.job]))
        return ingest(self.root, self.path, dry)

    def test_scoring_regression(self):
        self.assertEqual(score_job(self.job), dict(hard_reject=False, reject_reasons=[], qualification_score=90, career_fit_score=94, confidence=88))

    def test_identity_and_tracking_parameters(self):
        self.assertEqual(canonical_url('https://EXAMPLE.com/jobs/1/?utm_source=x#foo'), 'https://example.com/jobs/1')
        self.assertNotEqual(canonical_url('https://example.com/jobs?id=1'), canonical_url('https://example.com/jobs?id=2'))
        second = copy.deepcopy(self.job)
        second['url'] += '?utm_source=board'
        self.assertEqual(len(self.run_import([self.job, second])), 1)
        second['url'] = 'https://another.example/jobs/2'
        self.assertEqual(len(self.run_import([second])), 2)  # Same title is insufficient.

    def test_requisition_dedupe_and_ambiguity(self):
        self.job['requisition_id'] = 'ABC-123'
        first = self.run_import()
        second = copy.deepcopy(self.job)
        second['url'] = 'https://board.example/job/123'
        result = self.run_import([second])
        self.assertEqual(result[0]['id'], first[0]['id'])
        self.assertEqual(len(result[0]['sources']), 2)
        third = copy.deepcopy(second)
        third['requisition_id'] = 'different'
        third['url'] = 'https://board.example/job/456'
        self.run_import([third])
        third['requisition_id'] = 'ABC-123'
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.run_import([third])

    def test_repeat_import_preserves_human_fields(self):
        self.run_import()
        path = self.root / 'tracker.csv'
        with path.open(newline='') as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        rows[0].update(status='APPLIED', notes='Human, note\nsecond line', resume_version='v2')
        with path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        first = self.run_import()
        before = path.read_bytes()
        self.run_import()
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(first[0]['status'], 'APPLIED')
        self.assertIn('Human, note', path.read_text())

    def test_missing_information_and_validation(self):
        unknown = copy.deepcopy(self.job)
        unknown.update(salary_min=None, salary_max=None, confidence=.5)
        result = self.run_import([unknown])[0]
        self.assertEqual(result['scores']['career_fit_score'], 94)
        self.assertEqual(result['scores']['confidence'], 50)
        self.assertFalse(result['scores']['hard_reject'])
        for key, value in [('confidence', float('nan')), ('mandatory_relocation', 'false'), ('schema_version', True), ('salary_basis', 'hourly')]:
            bad = copy.deepcopy(self.job)
            bad[key] = value
            with self.assertRaises(ValueError):
                normalize(bad, self.tracks)
        del unknown['career_fit']['compensation']
        with self.assertRaises(ValueError):
            normalize(unknown, self.tracks)

    def test_rejection_stretch_and_career_first(self):
        stretch = copy.deepcopy(self.job)
        stretch['url'] += '/stretch'
        stretch['qualification'] = dict.fromkeys(stretch['qualification'], .65)
        stretch['career_fit'] = dict.fromkeys(stretch['career_fit'], 1)
        reject = copy.deepcopy(self.job)
        reject['url'] += '/reject'
        reject['major_organic_social_ownership'] = True
        result = self.run_import([self.job, stretch, reject])
        self.assertEqual(result[0]['candidate_group'], 'stretch')
        self.assertEqual(result[-1]['status'], 'REJECTED')
        with patch.dict(score_module.CONFIG['hard_filters'], {'minimum_known_base_salary':120000, 'maximum_domestic_trips_per_year':3}):
            for updates in ({'salary_min':119999}, {'mandatory_relocation':True}, {'domestic_trips_per_year':4}):
                self.assertTrue(score_job(dict(self.job, **updates))['hard_reject'])

    def test_invalid_batch_and_dry_run_do_not_write(self):
        original = (self.root / 'tracker.csv').read_bytes()
        self.run_import(dry=True)
        self.assertFalse((self.root / 'jobs').exists())
        with self.assertRaises(ValueError):
            self.run_import([self.job, {}])
        self.assertEqual(original, (self.root / 'tracker.csv').read_bytes())
        self.assertFalse((self.root / 'jobs').exists())

    def test_interrupted_write_recovery(self):
        with patch('find_jobs.apply_transaction', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.run_import()
        self.assertTrue((self.root / 'jobs/.discovery-transaction.json').exists())
        result = self.run_import()
        self.assertEqual(len(result), 1)
        self.assertFalse((self.root / 'jobs/.discovery-transaction.json').exists())


if __name__ == '__main__':
    unittest.main()

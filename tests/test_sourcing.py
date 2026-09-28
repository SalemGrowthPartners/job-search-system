import copy
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from find_jobs import ROOT, context, ingest, apply_transaction
from discovery import HEADER, normalize, merge
import sourcing
import provenance


class SourcingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for folder in ('profile','config'):
            shutil.copytree(ROOT/folder,self.root/folder)
        (self.root/'tracker.csv').write_text(','.join(HEADER)+'\n')
        self.lead=json.loads((ROOT/'templates/find/lead.example.json').read_text())[0]
        self.job=json.loads((ROOT/'templates/find/analysis.example.json').read_text())[0]
        self.run=json.loads((ROOT/'templates/find/run.example.json').read_text())
        self.path=self.root/'input.json'
        self.tracks=context(self.root)[1]

    def write(self,data):
        self.path.write_text(json.dumps(data));return self.path

    def snapshot(self):
        return {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p!=self.path}

    def stage(self,dry=False):
        return sourcing.stage(self.root,self.write([self.lead]),dry)

    def promote(self,dry=False):
        return ingest(self.root,self.write([self.job]),dry,promote=True)

    def test_plan_modes_rotation_and_no_writes(self):
        before=self.snapshot()
        standard=context(self.root)[0]['sourcing_plan']
        broad=context(self.root,'broad')[0]['sourcing_plan']
        self.assertEqual(len(broad['title_queries']),sum(len(t['searches']) for t in self.tracks.values()))
        self.assertEqual({q['track'] for q in standard['title_queries']},set(self.tracks))
        self.assertTrue(any(q['stretch'] for q in standard['capability_queries']))
        self.assertEqual(before,self.snapshot())
        self.run['completed']=True
        sourcing.record_run(self.root,self.write(self.run))
        new=context(self.root)[0]['sourcing_plan']
        self.assertNotEqual(standard['title_queries'],new['title_queries'])
        self.assertNotEqual(standard['sources'],new['sources'])
        self.assertEqual(new['since'],self.run['finished_at'])

    def test_staging_whole_batch_validation_and_dry_run(self):
        before=self.snapshot();self.stage(dry=True)
        self.assertEqual(before,self.snapshot())
        with self.assertRaises(ValueError):
            sourcing.stage(self.root,self.write([self.lead,{}]))
        self.assertEqual(before,self.snapshot())
        self.stage();self.stage()
        self.assertEqual(len(sourcing.load(self.root,'jobs/staging/leads.json',[])),1)
        self.assertEqual((self.root/'tracker.csv').read_text(),','.join(HEADER)+'\n')

    def test_promotion_requires_verification_and_preserves_origin(self):
        self.stage();before=self.snapshot()
        self.job['provenance']['availability']='unverified'
        with self.assertRaises(ValueError):self.promote()
        self.assertEqual(before,self.snapshot())
        self.job['provenance']['availability']='open'
        self.promote(dry=True);self.assertEqual(before,self.snapshot())
        rows=self.promote()
        self.assertEqual(rows[0]['provenance']['origin'],self.lead['provenance']['origin'])
        self.assertEqual(rows[0]['url'],self.job['url'])
        self.assertTrue(rows[0]['description_hash'])
        lead=sourcing.load(self.root,'jobs/staging/leads.json',[])[0]
        self.assertEqual(lead['promoted_job_id'],rows[0]['id'])
        self.assertEqual(lead['disposition'],'promoted')
        self.stage()
        self.assertEqual(sourcing.load(self.root,'jobs/staging/leads.json',[])[0]['disposition'],'promoted')

    def test_promotion_recovery_includes_leads(self):
        self.stage()
        with patch('find_jobs.apply_transaction',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):self.promote()
        self.assertTrue((self.root/'jobs/.discovery-transaction.json').exists())
        rows=self.promote()
        self.assertEqual(len(rows),1)
        self.assertEqual(sourcing.load(self.root,'jobs/staging/leads.json',[])[0]['promoted_job_id'],rows[0]['id'])
        self.assertFalse((self.root/'jobs/.discovery-transaction.json').exists())

    def test_legacy_origin_stays_unknown_and_human_status_survives(self):
        legacy=copy.deepcopy(self.job);legacy['schema_version']=1;legacy.pop('provenance')
        first=ingest(self.root,self.write([legacy]))[0]
        with (self.root/'tracker.csv').open(newline='') as f:
            rd=csv.DictReader(f);fields=rd.fieldnames;rows=list(rd)
        rows[0]['status']='APPLIED';rows[0]['notes']='Preserve'
        with (self.root/'tracker.csv').open('w',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(rows)
        refreshed=ingest(self.root,self.write([self.job]))[0]
        self.assertEqual(refreshed['id'],first['id'])
        self.assertIsNone(refreshed['provenance']['origin'])
        self.assertEqual(refreshed['status'],'APPLIED')
        self.assertTrue(refreshed['provenance']['observations'])

    def test_ats_namespace_identity_and_source_observations_not_keys(self):
        p=self.job['provenance'];p.update(ats_provider='ashby',ats_board_id='board',ats_posting_id='123')
        records=[];first=merge(records,normalize(self.job,self.tracks))
        other=copy.deepcopy(self.job);other['url']='https://example.com/new-path';other['provenance']['authoritative_posting_url']=other['url']
        self.assertEqual(merge(records,normalize(other,self.tracks))['id'],first['id'])
        other['provenance']['ats_board_id']='different';other['url']='https://example.com/another';other['provenance']['authoritative_posting_url']=other['url']
        merge(records,normalize(other,self.tracks))
        self.assertEqual(len(records),2)

    def test_timestamp_validation_and_older_verification(self):
        p=self.job['provenance']
        newer=copy.deepcopy(p);newer['last_verified_at']='2026-09-09T12:00:00Z';newer['application_url']='https://example.com/new'
        combined=provenance.combine(newer,p)
        self.assertEqual(combined['application_url'],newer['application_url'])
        for value in ('2026-09-08','bad',None):
            with self.assertRaises(ValueError):provenance.timestamp(value)
        bad=copy.deepcopy(self.job);bad['provenance']['application_url']='javascript:bad'
        with self.assertRaises(ValueError):normalize(bad,self.tracks)

    def test_coverage_report_and_immutable_runs(self):
        self.stage();self.promote()
        before=self.snapshot();sourcing.record_run(self.root,self.write(self.run),True)
        self.assertEqual(before,self.snapshot())
        sourcing.record_run(self.root,self.write(self.run))
        sourcing.record_run(self.root,self.write(self.run))
        self.run['completed']=True
        with self.assertRaises(ValueError):sourcing.record_run(self.root,self.write(self.run))
        report=sourcing.report(self.root)
        builtin=next(s for s in report['sources'] if s['source_id']=='builtin')
        self.assertEqual(builtin['unique_leads_seen'],1)
        self.assertEqual(builtin['originated_verified_records'],1)
        self.assertEqual(builtin['minutes'],5)
        self.assertEqual(report['pending_leads'],0)

    def test_new_origin_required_and_company_check_due_date(self):
        self.job['provenance']['origin']=None
        before=self.snapshot()
        with self.assertRaises(ValueError):ingest(self.root,self.write([self.job]))
        self.assertEqual(before,self.snapshot())
        # An empty starter watch list is valid; onboarding adds user-approved companies.
        self.assertEqual(sourcing.plan(self.root,self.tracks)['due_companies'], [])

    def test_unknown_sources_block_before_writes(self):
        self.job['provenance']['origin']['source_id']='not_registered'
        before=self.snapshot()
        with self.assertRaises(ValueError):ingest(self.root,self.write([self.job]))
        self.assertEqual(before,self.snapshot())

if __name__=='__main__':unittest.main()

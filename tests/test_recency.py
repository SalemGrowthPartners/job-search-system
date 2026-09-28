import copy
from datetime import date, timedelta
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from find_jobs import ROOT, context
from discovery import normalize, merge, HEADER
from score_job import score_job
import recency
import provenance


class RecencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for folder in ('profile','config'):
            shutil.copytree(ROOT/folder,self.root/folder)
        self.today=date(2026,9,8)
        self.policy=recency.policy(self.root)
        self.job=json.loads((ROOT/'templates/find/analysis.example.json').read_text())[0]
        self.tracks=context(self.root)[1]

    def record(self,age=None,fit=89):
        j=copy.deepcopy(self.job)
        if age is not None:
            j['provenance']['original_posted_at']=(self.today-timedelta(days=age)).isoformat()
            j['provenance']['original_posted_evidence']={'date_type':'original_published','raw_text':'Original posting date from employer','url':j['url'],'observed_at':'2026-09-08T20:00:00Z'}
        j['provenance']['last_verified_at']='2026-09-08T19:00:00Z'
        records=[];r=merge(records,normalize(j,self.tracks))
        r['scores']['career_fit_score']=fit
        return r

    def test_band_boundaries(self):
        for age,band in [(0,'highest'),(3,'highest'),(4,'high'),(7,'high'),(8,'normal'),(14,'normal'),(15,'reduced'),(30,'reduced'),(31,'older')]:
            self.assertEqual(recency.assess(self.record(age),self.policy,self.today)['recency_band'],band)

    def test_unknown_is_not_discovery_or_republish_age(self):
        r=self.record();r['date_posted']='2020-01-01';r['date_found']='2026-09-08'
        r['provenance']['source_published_at']='2026-09-08T12:00:00Z'
        r['provenance']['date_basis']='last_published'
        a=recency.assess(r,self.policy,self.today)
        self.assertIsNone(a['age_days']);self.assertEqual(a['priority_order'],2)

    def test_original_date_needs_evidence(self):
        j=copy.deepcopy(self.job);j['provenance']['original_posted_at']='2026-09-01'
        with self.assertRaises(ValueError):normalize(j,self.tracks)
        j['provenance']['original_posted_evidence']={'date_type':'updated'}
        with self.assertRaises(ValueError):normalize(j,self.tracks)

    def test_reimport_preserves_original_and_rejects_reset(self):
        old=self.record(20)['provenance'];new=copy.deepcopy(self.job['provenance'])
        new['source_published_at']='2026-09-08T12:00:00Z';new['date_basis']='last_published'
        combined=provenance.combine(old,new)
        self.assertEqual(combined['original_posted_at'],old['original_posted_at'])
        new['original_posted_at']='2026-09-08'
        with self.assertRaises(ValueError):provenance.combine(old,new)

    def test_scores_unchanged_with_recency(self):
        baseline=score_job(self.job)
        for age in (0,7,30,90,None):
            r=self.record(age);self.assertEqual(score_job(r),baseline)
            before=copy.deepcopy(r)
            recency.assess(r,self.policy,self.today)
            self.assertEqual(r,before)

    def test_older_reverification_and_evergreen_gate(self):
        r=self.record(31);r['provenance']['last_verified_at']='2026-08-01T12:00:00Z'
        self.assertTrue(recency.assess(r,self.policy,self.today)['verification_needed'])
        r['provenance']['last_verified_at']='2026-09-08T12:00:00Z'
        self.assertFalse(recency.assess(r,self.policy,self.today)['verification_needed'])
        r=self.record(61,94)
        self.assertTrue(recency.assess(r,self.policy,self.today)['verification_needed'])
        r['provenance'].update(evergreen_checked_at='2026-09-08T12:00:00Z',evergreen_check_evidence='Specific live vacancy, no talent-pool language.')
        a=recency.assess(r,self.policy,self.today)
        self.assertFalse(a['verification_needed']);self.assertEqual(a['priority_order'],1)

    def test_queue_highlights_and_human_state(self):
        records=[self.record(2,88),self.record(20,94),self.record(None,92),self.record(5,93)]
        for i,r in enumerate(records):r['id']=str(i)
        records[-1]['status']='APPLIED'
        (self.root/'jobs/discovered').mkdir(parents=True)
        path=self.root/'jobs/discovered/records.json';path.write_text(json.dumps(records))
        before=path.read_bytes()
        q=recency.queue(self.root,self.today)
        self.assertEqual([x['id'] for x in q['application_priority']],['0','1','2'])
        self.assertEqual(q['fit_order'],['1','2','0'])
        self.assertEqual(q['exceptional_older_matches'][0]['id'],'1')
        self.assertEqual(q['unknown_date_matches'][0]['id'],'2')
        self.assertEqual(q['excluded_ids'],['3']);self.assertEqual(path.read_bytes(),before)

    def test_search_windows_and_broad_undated_sweep(self):
        s=recency.search_plan(self.root,'2026-08-01T12:00:00Z','standard',self.today)
        self.assertEqual([w['label'] for w in s['windows']],['last_3_days','last_7_days','since_last_completed_run'])
        self.assertEqual(s['windows'][0]['from_date'],'2026-09-05')
        b=recency.search_plan(self.root,None,'broad',self.today)
        self.assertGreater(b['undated_search_effort_percent'],s['undated_search_effort_percent'])

    def test_conflicts_and_future_evidence(self):
        r=self.record(3);r['conflicts']=['location eligibility unresolved']
        self.assertTrue(recency.assess(r,self.policy,self.today)['verification_needed'])
        j=copy.deepcopy(self.job);j['provenance']['original_posted_at']='2026-10-01'
        j['provenance']['original_posted_evidence']={'date_type':'original_published','raw_text':'bad date','url':j['url'],'observed_at':'2026-09-08T12:00:00Z'}
        with self.assertRaises(ValueError):normalize(j,self.tracks)

if __name__=='__main__':unittest.main()

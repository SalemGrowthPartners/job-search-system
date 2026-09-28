import base64
import csv
import json
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
# Encoded so the audit terms themselves are not stored as cleartext in the package.
ENCODED=[
'QW5kcmV3IEhpY2tleQ==','OTBtaWxlc25vcnRoQGdtYWlsLmNvbQ==','NTE4LTc3OS05MTkw',
'S2VpemVy','RmFtaWx5IEhlbHAgJiBXZWxsbmVzcw==','VW5pZmFp','WWVsbG93YnJpY2sgTGVhcm5pbmc=',
'V2lsbGFtZXR0ZSBVbml2ZXJzaXR5IE1CQQ==','ZUNvcm5lbGw=','Q2hlcnJpb3Rz','Q2Fwc3VsZQ=='
]

class SanitizedStateTests(unittest.TestCase):
    def test_no_cleartext_personal_markers(self):
        banned=[base64.b64decode(x).decode().lower() for x in ENCODED]
        hits=[]
        for p in ROOT.rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts: continue
            if p.suffix.lower() in {'.pyc','.zip'}: continue
            try: text=p.read_text(errors='strict').lower()
            except (UnicodeDecodeError,OSError): continue
            for term in banned:
                if term in text: hits.append((str(p.relative_to(ROOT)),term))
        self.assertEqual(hits,[])

    def test_no_personal_state_or_application_materials(self):
        with (ROOT/'tracker.csv').open(newline='') as f: self.assertEqual(list(csv.DictReader(f)),[])
        self.assertEqual(json.loads((ROOT/'jobs/discovered/records.json').read_text()),[])
        self.assertEqual(json.loads((ROOT/'jobs/staging/leads.json').read_text()),[])
        self.assertEqual(json.loads((ROOT/'jobs/discovery-runs.json').read_text()),[])
        self.assertEqual([p for p in (ROOT/'applications').rglob('*') if p.is_file()],[])
        self.assertEqual([p for p in ROOT.rglob('*') if p.suffix.lower() in {'.docx','.pdf','.rtf'}],[])

    def test_profile_and_watch_list_start_blank(self):
        profile=yaml.safe_load((ROOT/'profile/master-profile.yaml').read_text())
        accomplishments=yaml.safe_load((ROOT/'profile/accomplishments.yaml').read_text())
        watch=yaml.safe_load((ROOT/'config/target-companies.yaml').read_text())
        self.assertEqual(profile['career_history'],[])
        self.assertEqual(profile['identity']['name'],None)
        self.assertEqual(accomplishments['accomplishments'],[])
        self.assertEqual(watch['companies'],[])

if __name__=='__main__': unittest.main()

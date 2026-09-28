import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import onboard

class OnboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for d in ('onboarding/source-documents','profile','config'): (self.root/d).mkdir(parents=True,exist_ok=True)
        (self.root/'onboarding/claim-review.yaml').write_text('schema_version: 1\nclaims: []\nconflicts: []\n')
        self.patches=[patch.object(onboard,'ROOT',self.root),patch.object(onboard,'SOURCE_DIR',self.root/'onboarding/source-documents'),patch.object(onboard,'LEDGER',self.root/'onboarding/claim-review.yaml')]
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def test_multiple_source_intake_hashes_and_deduplicates(self):
        a=self.root/'a.pdf'; b=self.root/'b.docx'; a.write_bytes(b'one'); b.write_bytes(b'two')
        added=onboard.intake([a,b],'resume')
        self.assertEqual(len(added),2)
        duplicate=onboard.intake([a],'resume')[0]
        self.assertTrue(duplicate['duplicate'])
        inv=json.loads((self.root/'onboarding/source-inventory.json').read_text())
        self.assertEqual(len(inv),2)
        self.assertTrue(all((self.root/'onboarding/source-documents'/x['stored_name']).exists() for x in inv))

    def test_confirmed_claim_requires_user_confirmation(self):
        data={'schema_version':1,'claims':[{'id':'c1','status':'confirmed','source_refs':['resume-01']}],'conflicts':[]}
        (self.root/'onboarding/claim-review.yaml').write_text(yaml.safe_dump(data))
        with self.assertRaises(ValueError): onboard.validate_ledger()
        data['claims'][0]['user_confirmation']='Confirmed during onboarding stage 3.'
        (self.root/'onboarding/claim-review.yaml').write_text(yaml.safe_dump(data))
        onboard.validate_ledger()

    def test_disputed_claim_blocks_finalize(self):
        src=self.root/'resume.pdf'; src.write_bytes(b'evidence'); onboard.intake([src],'resume')
        data={'schema_version':1,'claims':[{'id':'c1','status':'disputed','source_refs':['resume-01']}],'conflicts':[]}
        (self.root/'onboarding/claim-review.yaml').write_text(yaml.safe_dump(data))
        self.assertFalse(onboard.status()['ready_to_finalize'])
        with self.assertRaises(ValueError): onboard.finalize()

    def test_finalize_requires_complete_reviewed_configuration(self):
        src=self.root/'resume.pdf'; src.write_bytes(b'evidence'); onboard.intake([src],'resume')
        for rel in ('profile/master-profile.yaml','profile/accomplishments.yaml','profile/preferences.yaml','config/search-tracks.yaml','config/scoring.yaml','config/capability-queries.yaml','config/target-companies.yaml'):
            (self.root/rel).write_text('onboarding_status: complete\n')
        result=onboard.finalize()
        self.assertTrue(result['ready'])
        self.assertIn('/find',result['next_commands'])

if __name__=='__main__': unittest.main()

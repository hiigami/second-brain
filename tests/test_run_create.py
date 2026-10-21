"""Bounded synthetic preparation and verified-only recovery; never real capture."""
import copy
import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from test_targeting import TargetFixture
import test_run_context as context_tests
from second_brain.kb_common import KBError, read_json
from second_brain.kb_run import create_run, STAGES


class RunCreateTests(TargetFixture):
    def setUp(self):
        super().setUp()
        self.request_path=self.root/'run-request.json'
        self.save(self.request_path,self.request)

    def create(self,**kwargs):
        return create_run(self.config,self.request_path,'one',**kwargs)

    def test_dry_run_is_read_only_and_does_not_open_source_content(self):
        from second_brain import kb_inventory
        with patch.object(kb_inventory,'read_stable',side_effect=AssertionError('No capture reads in dry-run')):
            result=self.create(dry_run=True)
        self.assertEqual(result['status'],'dry_run')
        self.assertTrue(result['first_run'])
        self.assertFalse((self.root/'home/runs').exists())
        self.assertEqual(result['context'],'explicit_none')

    def test_first_run_prepares_manual_handoff_and_resume_preserves_bytes(self):
        result=self.create()
        run=self.root/'home/runs/one'
        self.assertEqual(result['status'],'prepared_for_manual_extraction')
        self.assertEqual(result['publication'],'blocked_analysis_only')
        receipt=read_json(run/'work/preparation.json')
        self.assertEqual(receipt['status'],'ready')
        self.assertEqual(list(receipt['stages']),list(STAGES))
        self.assertFalse((run/'proposals/records.json').exists())
        self.assertFalse((self.root/'home/knowledge/approved/CURRENT.json').exists())
        before={str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()}
        self.assertEqual(self.create(resume=True),result)
        self.assertEqual(before,{str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(KBError,'already exists'):
            self.create()

    def test_changed_output_scope_or_source_blocks_resume_without_rewrite(self):
        self.create()
        run=self.root/'home/runs/one'
        snapshot=(run/'manifest.json').read_bytes()
        packet=next((run/'packets').glob('packet-*.md'))
        original=packet.read_bytes();packet.write_text('Tampered')
        with self.assertRaisesRegex(KBError,'outputs changed'):
            self.create(resume=True)
        packet.write_bytes(original)
        self.request['purpose']='project_refresh'
        self.save(self.request_path,self.request)
        with self.assertRaisesRegex(KBError,'inputs changed'):
            self.create(resume=True)
        self.request['purpose']='analysis_only';self.save(self.request_path,self.request)
        self.export.write_text('Source changed')
        with self.assertRaisesRegex(KBError,'Live source changed'):
            self.create(resume=True)
        self.assertEqual((run/'manifest.json').read_bytes(),snapshot)

    def test_interrupted_packet_stage_cannot_overwrite_or_recapture(self):
        from second_brain import kb_run
        original=kb_run.build_packets
        def crash(run):
            original(run)
            raise KBError('Synthetic interruption after packet commit')
        with patch.object(kb_run,'build_packets',side_effect=crash):
            with self.assertRaisesRegex(KBError,'interruption'):
                self.create()
        run=self.root/'home/runs/one'
        before=(run/'manifest.json').read_bytes()
        with self.assertRaisesRegex(KBError,'Interrupted stage packets'):
            self.create(resume=True)
        self.assertEqual((run/'manifest.json').read_bytes(),before)
        self.assertEqual(read_json(run/'work/preparation.json')['stages']['packets']['status'],'running')

    def test_resume_rejects_completed_receipt_that_omits_required_output(self):
        self.create()
        run=self.root/'home/runs/one'
        state=read_json(run/'work/preparation.json')
        del state['stages']['packets']['outputs']['packets/coverage-stub.json']
        self.save(run/'work/preparation.json',state)
        before={str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(KBError,'receipt omits required outputs'):
            self.create(resume=True)
        self.assertEqual(before,{str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()})

    def test_create_run_resume_omitting_indexed_packet_is_rejected_without_rewrite(self):
        self.create()
        run=self.root/'home/runs/one'
        state=read_json(run/'work/preparation.json')
        packet=next((run/'packets').glob('packet-*.md'))
        original=packet.read_bytes()
        for mutation in ('unchanged','altered','deleted'):
            with self.subTest(mutation=mutation):
                packet.write_bytes(original)
                receipt=copy.deepcopy(state)
                del receipt['stages']['packets']['outputs'][packet.relative_to(run).as_posix()]
                self.save(run/'work/preparation.json',receipt)
                if mutation=='altered': packet.write_text('Altered synthetic packet.')
                if mutation=='deleted': packet.unlink()
                before={str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()}
                with self.assertRaisesRegex(KBError,'packet outputs'):
                    self.create(resume=True)
                self.assertEqual(before,{str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()})

    def test_create_run_resume_unexpected_packet_output_is_rejected(self):
        self.create()
        run=self.root/'home/runs/one'
        extra=run/'packets/unexpected.md'
        extra.write_text('Unexpected synthetic packet.')
        with self.assertRaisesRegex(KBError,'packet outputs'):
            self.create(resume=True)
        self.assertEqual(extra.read_text(),'Unexpected synthetic packet.')

    def test_only_verified_completed_prefix_can_continue(self):
        self.create()
        run=self.root/'home/runs/one'
        state=read_json(run/'work/preparation.json')
        # Synthetic interruption strictly between completed stages; remove later receipts/artifacts.
        state['status']='preparing'
        for name in list(STAGES)[2:]:
            for rel in state['stages'][name]['outputs']:
                (run/rel).unlink()
            del state['stages'][name]
        self.save(run/'work/preparation.json',state)
        manifest_bytes=(run/'manifest.json').read_bytes()
        with patch('second_brain.kb_run.inventory',side_effect=AssertionError('Never recapture')):
            self.create(resume=True)
        self.assertEqual((run/'manifest.json').read_bytes(),manifest_bytes)
        self.assertEqual(read_json(run/'work/preparation.json')['status'],'ready')

    def test_create_run_delayed_resume_preserves_completed_receipt(self):
        from second_brain import kb_run
        self.create()
        run=self.root/'home/runs/one'
        state=read_json(run/'work/preparation.json')
        state['status']='preparing'
        for name in list(STAGES)[2:]:
            for rel in state['stages'][name]['outputs']:
                (run/rel).unlink()
            del state['stages'][name]
        self.save(run/'work/preparation.json',state)
        original=kb_run.write_json_new
        completed=[]
        finished_bytes={}
        def finish_competing_resume(path,value):
            # Both callers validated the prefix; the competitor finishes before
            # this caller acquires the now-free lock.
            if path==run/'.preparation.lock' and not completed:
                completed.append(None)
                completed[0]=self.create(resume=True)
                finished_bytes.update({str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()})
            return original(path,value)
        with patch.object(kb_run,'write_json_new',side_effect=finish_competing_resume):
            with self.assertRaisesRegex(KBError,'receipt changed'):
                self.create(resume=True)
        self.assertEqual(completed[0]['status'],'prepared_for_manual_extraction')
        self.assertEqual(finished_bytes,{str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()})
        self.assertEqual(self.create(resume=True),completed[0])

    def test_requested_context_failure_stops_before_capture(self):
        self.request['context']={'access_path':str(self.root/'missing.json'),'registry_path':str(self.registry_path),
            'project_configs':[str(self.config)],'permission_path':str(self.root/'absent-permission.json'),
            'queries':['needed'],'max_records':1,'max_bytes':100000,'required_keys':[],'expand_relations':0}
        self.save(self.request_path,self.request)
        with self.assertRaises((KBError,OSError)):
            self.create()
        self.assertFalse((self.root/'home/runs/one').exists())

    def test_cli_dispatches_run_create_dry_run(self):
        from second_brain.cli import main
        out=io.StringIO()
        with patch.object(sys,'argv',['second-brain','run','create','--project',str(self.config),
            '--request',str(self.request_path),'--run-id','one','--dry-run']),redirect_stdout(out):
            with self.assertRaises(SystemExit) as exit:
                main()
        self.assertEqual(exit.exception.code,0)
        self.assertIn('dry_run',out.getvalue())


class RunCreateContextTests(unittest.TestCase):
    def setUp(self):
        self.fixture=context_tests.RunContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture
        self.path=self.f.root/'run-request.json'
        self.f.save(self.path,self.f.request)

    def test_authorized_context_preparation_and_unrelated_index_refresh_resume(self):
        f=self.f
        result=create_run(f.config,self.path,'one')
        run=f.root/'home/runs/one'
        self.assertIn('demob:one:REQ-001',(run/'work/assistant-briefing.md').read_text())
        self.assertEqual(read_json(run/'work/preparation-check.json')['context_check'],'prospective')
        f.index_fixture.release('home','two')
        f.index_fixture.build()
        self.assertEqual(create_run(f.config,self.path,'one',resume=True),result)
        f.index_fixture.release('demob','two')
        with self.assertRaisesRegex(KBError,'changed'):
            create_run(f.config,self.path,'one',resume=True)

    def test_legacy_file_level_approved_records_upgrade_to_targeted_preparation(self):
        f=self.f.index_fixture
        for version in ('0.1','0.2'):
            prior,records=f.candidate('home','legacy-'+version.replace('.','-'))
            records['schema_version']=version
            records.pop('segment_coverage')
            for r in records['records']:
                r.pop('events')
                for e in r['evidence']:
                    e.pop('segment_id');e.pop('representation_sha256')
            f.save(prior/'proposals/records.json',records)
            f.synthetic_publish('home',prior)
            req=copy.deepcopy(self.f.request)
            req['context']=None
            req['registry_path']=str(f.registry_path)
            req['selection'][0].update(source_id='notes',relative_path='notes.md',sha256=None,provenance=None)
            req['capture_mode']='whole_file'
            path=f.root/('legacy-request-'+version+'.json')
            f.save(path,req)
            run_id='prepared-'+version.replace('.','-')
            result=create_run(f.configs['home'],path,run_id)
            run=f.configs['home'].parent.parent/'runs'/run_id
            self.assertEqual(result['status'],'prepared_for_manual_extraction')
            suggestion=read_json(run/'work/reanchored-records.json')
            self.assertEqual(suggestion['schema_version'],'0.6')
            self.assertIn('segment_coverage',suggestion)
            self.assertIn('segment_id',suggestion['records'][0]['evidence'][0])
            self.assertEqual(suggestion['records'][0]['attribution'][0]['class'],'unknown')

    def test_target_own_prior_context_survives_its_successful_publication(self):
        from second_brain.kb_common import json_sha, sha
        from second_brain.kb_referrals import load_approved_release
        from second_brain.kb_check import check_run
        f=self.f.index_fixture
        config=f.configs['home']
        req=copy.deepcopy(self.f.request)
        req['capture_mode']='whole_file'
        req['registry_path']=str(f.registry_path)
        req['selection'][0].update(relative_path='notes.md',sha256=None,provenance=None)
        req['purpose']='project_refresh'
        req['context'].update(queries=['SYNTH-home'],required_keys=['home:one:REQ-001'])
        run_id='own-context'
        permission=copy.deepcopy(self.f.permission)
        permission.update(run_id=run_id,project_ids=['home'],run_path=str(config.parent.parent/'runs'/run_id),
            release_path=str(config.parent.parent/'knowledge/approved'/run_id))
        self.f.save(self.f.permission_path,permission)
        request_path=f.root/'own-request.json';f.save(request_path,req)
        result=create_run(config,request_path,run_id)
        run=config.parent.parent/'runs'/run_id
        self._candidate_for_run(f,run,run_id)
        release=f.synthetic_publish('home',run)
        self.assertEqual(load_approved_release(config)['run_id'],run_id)
        self.assertEqual(check_run(release,release/'records.json',historical=True,stage2=True)['status'],'passed')
        self.assertEqual((release/'work/context.json').read_bytes(),(run/'work/context.json').read_bytes())
        f.build()
        self.assertTrue(f.output.is_file())

    def _candidate_for_run(self,f,run,run_id,foreign=False):
        from second_brain.kb_common import json_sha, sha
        data=read_json(run/'packets/coverage-stub.json')
        file=read_json(run/'manifest.json')['files'][0]
        segment=read_json(run/'segments.snapshot.json')['segments'][0]
        lines=(run/file['snapshot_path']).read_text().splitlines()
        cite={'evidence_id':file['evidence_id'],'segment_id':segment['segment_id'],
            'representation_sha256':segment['representation_sha256'],'start_line':1,'end_line':len(lines),
            'quote':'\n'.join(lines)}
        r={'id':'REQ-001','kind':'requirement','title':'Synthetic request','statement':'Review remains proposed.',
            'epistemic_status':'proposal','evidence':[cite],'relations':[],'open_questions':[],'investigation':None,
            'events':[],'cross_project':[],'aliases':[],'assertions':[],
            'attribution':[{'evidence_ref':0,'class':'home','project_id':'home','reason':'Synthetic home source.'}]}
        data['records']=[r]
        for name in ('coverage','segment_coverage','interval_coverage'):
            for row in data[name]:row['disposition']='used'
        referrals={'schema_version':'1.1','project_id':'home','run_id':run_id,'registry_sha256':json_sha(f.registry),
            'mentions_sha256':sha((run/'work/mentions.json').read_bytes()),'assessments':[],'referrals':[],'manual_mentions':[]}
        if foreign:
            r['cross_project']=[{'project_id':'demob','reason':'Synthetic shared constraint.','target_record':'demob:one:REQ-001'}]
            r['attribution'][0].update(**{'class':'R4','project_id':'demob'})
            r['assertions']=[{'type':'depends_on','target':{'project_id':'demob','run_id':'one','record_id':'REQ-001'},
                'evidence_refs':[0],'status':'proposal','reason':'Synthetic reviewed proposal only.'}]
            manual={'target_project_id':'demob','source':cite,'reason':'Synthetic manually assessed shared component.'}
            mid='M-'+json_sha(['manual',cite,'demob'])[:24]
            referrals['manual_mentions']=[manual]
            referrals['assessments']=[{'mention_id':mid,'class':'R4','disposition':'unresolved','reason':'Ownership unresolved.',
                'home_record_ids':['REQ-001'],'referral_id':None}]
        f.save(run/'proposals/records.json',data)
        f.save(run/'proposals/referrals.json',referrals)

    def test_foreign_assertions_resolve_only_in_authorized_derived_views(self):
        from second_brain.kb_reconciliation import assertion_views
        f=self.f.index_fixture
        f.registry['disclosures']=[{'from_project':'home','to_project':'demob','source_id':'notes','path_pattern':'notes.md'}]
        f.save(f.registry_path,f.registry)
        req=copy.deepcopy(self.f.request)
        req.update(context=None,capture_mode='whole_file',purpose='project_refresh',registry_path=str(f.registry_path))
        req['selection'][0].update(relative_path='notes.md',sha256=None,provenance=None)
        path=f.root/'assertion-request.json';f.save(path,req)
        config=f.configs['home'];run_id='assertions'
        target_bytes=(f.releases['demob']/'records.json').read_bytes()
        create_run(config,path,run_id)
        run=config.parent.parent/'runs'/run_id
        self._candidate_for_run(f,run,run_id,foreign=True)
        release=f.synthetic_publish('home',run)
        view=assertion_views(f.build())
        row=view['assertions'][0]
        self.assertEqual(row['owner'],'home:assertions:REQ-001')
        self.assertEqual(row['target_status'],'current')
        self.assertEqual(row['assertion']['status'],'proposal')
        self.assertEqual((f.releases['demob']/'records.json').read_bytes(),target_bytes)
        self.assertIn('manual reference',(release/'review-report.md').read_text())

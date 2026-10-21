"""Synthetic context permissions, selected freshness and historical integrity."""
import copy
import unittest
from unittest.mock import patch
from test_targeting import TargetFixture
import test_targeting as targeting
import test_global_index as global_index
import test_reconciliation as reconciliation
from second_brain.kb_common import KBError, read_json, sha, utc_now
from second_brain.kb_context import prepare_context, check_context
from second_brain.kb_check import check_run, load_manifest
from second_brain.kb_inventory import inventory
from second_brain.kb_index import query_index, query_verified, query_batch
from second_brain.kb_publish import prepare_review, publish


class RunContextTests(TargetFixture):
    def setUp(self):
        super().setUp()
        self.index_fixture=global_index.GlobalIndexTests()
        self.index_fixture.setUp()
        self.addCleanup(self.index_fixture.doCleanups)
        f=self.index_fixture
        f.build()
        self.permission_path=self.root/'context-permission.json'
        self.permission={'schema_version':'1.0','target_project_id':'home','run_id':'one',
            'project_ids':['demob'],'run_path':str(self.root/'home/runs/one'),
            'release_path':str(self.root/'home/knowledge/approved/one'),
            'copy_quotes':True,'copy_briefing':True,'retain_audit':True,
            'retention_reason':'Synthetic audit only','authorized_by':'Synthetic operator','authorized_at':utc_now()}
        self.save(self.permission_path,self.permission)
        self.request['context']={'access_path':str(f.access_path),'registry_path':str(f.registry_path),
            'project_configs':[str(p) for p in f.configs.values()], 'permission_path':str(self.permission_path),
            'queries':['SYNTH-demob'], 'max_records':10,'max_bytes':100000,
            'required_keys':['demob:one:REQ-001'],'expand_relations':0}

    def capture(self,name='one',**kwargs):
        bundle=prepare_context(self.config,name,self.request)
        return inventory(self.config,name,request=self.request,context_bundle=bundle,**kwargs)

    def test_context_is_exact_reproducible_and_separate_from_current_evidence(self):
        a=prepare_context(self.config,'one',self.request)
        b=prepare_context(self.config,'one',self.request)
        self.assertEqual(a,b)
        self.assertEqual(a['results'][0]['entry']['key'],'demob:one:REQ-001')
        self.assertIn('NOT CURRENT-RUN EVIDENCE',a['briefing'])
        run,m=self.capture()
        self.assertEqual(check_run(run)['context_check'],'prospective')
        self.assertEqual(read_json(run/'work/context.json'),a)
        self.assertEqual(m['targeted']['context_sha256'],sha((run/'work/context.json').read_bytes()))
        self.assertEqual(check_context(run,m)['context_check'],'frozen_integrity')

    def test_index_permission_alone_or_wrong_retained_destination_is_insufficient(self):
        for change in ('project','release','audit'):
            permission=copy.deepcopy(self.permission)
            if change=='project': permission['project_ids']=['home']
            if change=='release': permission['release_path']=str(self.root/'elsewhere/one')
            if change=='audit': permission['retain_audit']=False
            self.save(self.permission_path,permission)
            with self.subTest(change=change),self.assertRaises(KBError):
                prepare_context(self.config,'one',self.request)

    def test_required_context_budget_and_missing_keys_block_without_fallback(self):
        for change in ('budget','missing'):
            req=copy.deepcopy(self.request)
            if change=='budget': req['context']['max_bytes']=1000
            else: req['context']['required_keys']=['demob:one:REQ-999']
            with self.subTest(change=change),self.assertRaisesRegex(KBError,'[Rr]equired|budget'):
                prepare_context(self.config,'one',req)

    def test_foreign_change_blocks_prospective_but_not_frozen_history(self):
        run,m=self.capture()
        before=(run/'work/context.json').read_bytes()
        f=self.index_fixture
        f.release('demob','two')
        with self.assertRaisesRegex(KBError,'changed'):
            check_run(run)
        self.assertEqual(check_run(run,historical=True)['status'],'passed')
        self.permission_path.unlink()
        f.access_path.unlink()
        f.registry_path.unlink()
        self.assertEqual(check_run(run,historical=True)['status'],'passed')
        self.assertEqual((run/'work/context.json').read_bytes(),before)

    def test_unrelated_index_generation_change_does_not_invalidate_selected_context(self):
        run,m=self.capture()
        f=self.index_fixture
        f.release('home','two')
        f.build()
        self.assertEqual(check_run(run)['status'],'passed')

    def test_revocation_and_tampering_block_live_use_review_and_publication(self):
        run,m,data,_,_=targeting.TargetPassageTests.prepare_candidate(self,'project_refresh')
        self.permission['retention_reason']='Changed permission'
        self.save(self.permission_path,self.permission)
        with self.assertRaisesRegex(KBError,'permission changed'):
            prepare_review(self.config,run)
        self.assertEqual(check_run(run,run/'proposals/records.json',historical=True)['status'],'passed')
        context=read_json(run/'work/context.json');context['briefing']='Altered'
        self.save(run/'work/context.json',context)
        with self.assertRaisesRegex(KBError,'checksum'):
            load_manifest(run)

    def test_context_freshness_rechecked_before_target_pointer_swap(self):
        from second_brain import kb_publish
        run,m,data,_,_=targeting.TargetPassageTests.prepare_candidate(self,'project_refresh')
        original=kb_publish.render_views
        def changed(*args,**kwargs):
            with patch.object(kb_publish,'render_views',original):
                self.index_fixture.release('demob','two')
            return original(*args,**kwargs)
        with patch.object(kb_publish,'render_views',side_effect=changed):
            with self.assertRaisesRegex(KBError,'changed'):
                reconciliation.ReconciliationTests.synthetic_publish(self,run)
        self.assertFalse((self.root/'home/knowledge/approved/CURRENT.json').exists())
        self.assertTrue((run/'manifest.json').is_file())

    def test_successful_target_publication_retains_context_after_revocation(self):
        run,m,data,_,_=targeting.TargetPassageTests.prepare_candidate(self,'project_refresh')
        release=reconciliation.ReconciliationTests.synthetic_publish(self,run)
        self.permission_path.unlink()
        self.index_fixture.release('demob','two')
        self.assertEqual(check_run(release,release/'records.json',stage2=True,historical=True)['status'],'passed')
        self.assertEqual((release/'work/context.json').read_bytes(),(run/'work/context.json').read_bytes())

    def test_ranked_aliases_ties_expansion_filters_and_batch_verify_once(self):
        f=self.index_fixture
        data=f.build()
        rows=copy.deepcopy(data['entries'])
        rows[0]['record']['aliases']=['special-synonym']
        rows[0]['record']['relations']=[{'type':'depends_on','target':'REQ-002'}]
        extra=copy.deepcopy(rows[0]);extra['key']=extra['key'].replace('REQ-001','REQ-002');extra['record_id']='REQ-002'
        extra['record'].update(id='REQ-002',title='Different',statement='Distinct',aliases=[],relations=[],open_questions=[],events=[],epistemic_status='proposal')
        derived=copy.deepcopy(data);derived['entries']=rows+[extra]
        result=query_verified(derived,text='special-synonym',limit=1,expand_relations=1)
        self.assertEqual(result['total_matches'],2)
        self.assertEqual(result['omitted_count'],1)
        self.assertEqual(result['results'][0]['ranking_reasons'][0]['fields'],['aliases'])
        filtered=query_verified(derived,text='special-synonym',epistemic_status='observed',expand_relations=1)
        self.assertEqual(filtered['total_matches'],1)
        ties=query_verified(data,text='request')
        self.assertEqual([r['entry']['key'] for r in ties['results']],sorted(e['key'] for e in data['entries']))
        from second_brain import kb_index
        original=kb_index._verified
        with patch.object(kb_index,'_verified',wraps=original) as verified:
            batch=query_batch(f.access_path,f.registry_path,list(f.configs.values()),['request','proposed'])
            self.assertEqual(verified.call_count,1)
            self.assertEqual(len(batch['queries']),2)

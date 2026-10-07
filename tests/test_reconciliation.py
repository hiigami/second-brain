"""Synthetic complete-state and qualified assertion safeguards."""
import copy
import unittest
from test_targeting import TargetFixture
import test_targeting as targeting
from second_brain.kb_common import KBError, read_json, sha, utc_now
from second_brain.kb_check import check_run
from second_brain.kb_publish import prepare_review, publish
from second_brain.kb_reanchor import reanchor
from second_brain.kb_reconciliation import reconciliation_report, assertion_views


class ReconciliationTests(TargetFixture):
    def prepared(self):
        return targeting.TargetPassageTests.prepare_candidate(self,'project_refresh')

    def synthetic_publish(self,run):
        review=prepare_review(self.config,run)
        review.update(decision='approve',reviewer='Synthetic test reviewer',reviewed_at=utc_now(),notes='UNIT TEST ONLY')
        review['checks']=dict.fromkeys(review['checks'],True)
        review['acknowledged_warnings']=review['warning_summary']['counts']
        review['triage_acknowledged']=review['segment_triage_acknowledged']=True
        self.save(run/'review.json',review)
        return publish(self.config,run,run/'review.json',human_approved=True)

    def test_routed_reanchor_only_suggests_citations_and_requires_new_routing(self):
        run,m,data,_,_=self.prepared()
        release=self.synthetic_publish(run)
        new,new_m=self.capture('two',baseline=run)
        with self.assertRaisesRegex(KBError,'cannot be re-anchored'):
            reanchor(release,new)
        candidate,report=reanchor(release,new,citation_only=True)
        self.assertEqual(candidate['schema_version'],'0.6')
        self.assertTrue(report['routing_reassessment_required'])
        self.assertEqual(candidate['records'][0]['cross_project'],[])
        self.assertEqual(candidate['records'][0]['assertions'],[])
        self.assertEqual(candidate['records'][0]['attribution'][0]['class'],'unknown')
        self.save(new/'proposals/records.json',candidate)
        with self.assertRaises((KBError,OSError)):
            check_run(new,new/'proposals/records.json',stage2=True)

    def test_retained_and_missing_prior_support_are_reported_not_deleted(self):
        run,m,data,_,_=self.prepared()
        report=reconciliation_report(run,m,data,data,m)
        self.assertEqual(report['rows'][0]['status'],'retained')
        self.export.write_text('Changed context with no old claim.\n')
        self.request['selection'][0]['sha256']=sha(self.export.read_bytes())
        self.request['packets']['ranges']=[]
        new,new_m=self.capture('two',baseline=run)
        empty=dict(data,run_id='two',records=[])
        report=reconciliation_report(new,new_m,empty,data,m)
        self.assertEqual(report['rows'][0]['status'],'removed')
        self.assertTrue(report['rows'][0]['unsupported_prior_citations'])
        self.assertIn('human-reviewed removal',report['rows'][0]['action'])
        self.assertTrue((run/'proposals/records.json').is_file())

    def test_reanchor_citations_outside_selected_passages_are_reported_and_omitted(self):
        run,m,data,_,_=self.prepared()
        release=self.synthetic_publish(run)
        self.request['packets']['ranges']=[{'source_id':'notes','relative_path':'export.md','start_line':4,'end_line':4}]
        new,_=self.capture('two',baseline=run)
        candidate,report=reanchor(release,new,citation_only=True)
        self.assertEqual(candidate['records'],[])
        self.assertEqual(report['dropped_record_ids'],['REQ-001'])
        self.assertEqual(report['citations'][0]['status'],'outside_selected_passages')
        self.assertEqual(read_json(new/'work/reanchored-records.json')['records'],[])

    def test_reanchor_duplicate_quote_uses_only_selected_match(self):
        run,m,data,_,_=self.prepared()
        release=self.synthetic_publish(run)
        self.export.write_text(self.export.read_text()+data['records'][0]['evidence'][0]['quote']+'\n')
        self.request['selection'][0]['sha256']=sha(self.export.read_bytes())
        self.request['packets']['ranges']=[{'source_id':'notes','relative_path':'export.md','start_line':5,'end_line':7}]
        new,_=self.capture('two',baseline=run)
        candidate,report=reanchor(release,new,citation_only=True)
        self.assertEqual(candidate['records'][0]['evidence'][0]['start_line'],5)
        self.assertEqual(candidate['records'][0]['evidence'][0]['end_line'],7)
        self.assertEqual(report['citations'][0]['new_lines'],[5,7])

    def test_assertions_validate_evidence_indexes_and_local_targets(self):
        run,m,data,_,_=self.prepared()
        r=data['records'][0]
        r['assertions']=[{'type':'depends_on','target':{'project_id':'home','run_id':'one','record_id':'REQ-002'},
            'evidence_refs':[0],'status':'proposal','reason':'Explicit synthetic proposal.'}]
        for bad in ('dangling','evidence'):
            candidate=copy.deepcopy(data)
            if bad=='evidence':candidate['records'][0]['assertions'][0]['evidence_refs']=[9]
            self.save(run/'proposals/records.json',candidate)
            with self.subTest(bad=bad),self.assertRaises(KBError):
                check_run(run,run/'proposals/records.json')
        second=copy.deepcopy(r);second.update(id='REQ-002',assertions=[])
        data['records'].append(second)
        self.save(run/'proposals/records.json',data)
        result=check_run(run,run/'proposals/records.json')
        self.assertEqual(result['assertion_hints'][0]['target_integrity'],'local_candidate')

    def test_grouped_assertions_preserve_cycles_disagreements_and_unavailable_targets(self):
        def entry(pid, target_pid, relation):
            target={'project_id':target_pid,'run_id':'one','record_id':'REQ-001'}
            return {'key':f'{pid}:one:REQ-001','visibility':'current', 'record':{'assertions':[
                {'type':relation,'target':target,'evidence_refs':[0],'status':'observed','reason':'Synthetic'}]}}
        a,b=entry('a','b','supersedes'),entry('b','a','supersedes')
        a['record']['assertions'].append({'type':'conflicts_with','target':{'project_id':'b','run_id':'one','record_id':'REQ-001'},
            'evidence_refs':[0],'status':'unresolved','reason':'Unresolved disagreement.'})
        missing=entry('c','unavailable','depends_on')
        before=copy.deepcopy([a,b,missing])
        view=assertion_views({'entries':[a,b,missing]})
        self.assertEqual(sum(r['supersession_cycle'] for r in view['assertions']),2)
        self.assertTrue(view['assertions'][0]['opposing_assertions'])
        self.assertEqual(view['assertions'][-1]['target_status'],'unavailable_or_outside_selection')
        self.assertEqual([a,b,missing],before)
        view=assertion_views({'entries':[entry('a','b','equivalent_to'),entry('b','a','equivalent_to')]})
        self.assertEqual(view['equivalence_groups'],[['a:one:REQ-001','b:one:REQ-001']])

    def test_long_supersession_chain_does_not_depend_on_python_recursion_limit(self):
        entries=[]
        for i in range(1100):
            key=f'home:one:REQ-{i:04d}'
            assertion={'type':'supersedes','target':{'project_id':'home','run_id':'one','record_id':f'REQ-{i+1:04d}'},
                'evidence_refs':[0],'status':'observed','reason':'Synthetic chain'}
            entries.append({'key':key,'visibility':'current','record':{'assertions':[assertion]}})
        view=assertion_views({'entries':entries})
        self.assertEqual(len(view['assertions']),1100)
        self.assertFalse(any(a['supersession_cycle'] for a in view['assertions']))

    def test_assertion_views_mixed_status_supersession_does_not_report_cycle(self):
        def entry(owner,target,status):
            return {'key':f'home:one:{owner}','visibility':'current','record':{'assertions':[
                {'type':'supersedes','target':{'project_id':'home','run_id':'one','record_id':target},
                 'evidence_refs':[0],'status':status,'reason':'Synthetic status regression.'}]}}
        for status in ('proposal','unresolved'):
            for established in ('observed','interpretation'):
                for first in (True,False):
                    with self.subTest(status=status,established=established,first=first):
                        statuses=(status,established) if first else (established,status)
                        data={'entries':[entry('REQ-001','REQ-002',statuses[0]),
                                         entry('REQ-002','REQ-001',statuses[1])]}
                        before=copy.deepcopy(data)
                        view=assertion_views(data)
                        self.assertEqual([row['supersession_cycle'] for row in view['assertions']],[False,False])
                        self.assertEqual([row['assertion']['status'] for row in view['assertions']],list(statuses))
                        self.assertEqual(data,before)
        for first in ('observed','interpretation'):
            for second in ('observed','interpretation'):
                with self.subTest(first=first,second=second):
                    view=assertion_views({'entries':[entry('REQ-001','REQ-002',first),
                                                    entry('REQ-002','REQ-001',second)]})
                    self.assertEqual([row['supersession_cycle'] for row in view['assertions']],[True,True])

"""Opt-in targeted capture fixtures and synthetic authorization invariants."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from second_brain.kb_common import KBError, json_sha, read_json, sha, utc_now
from second_brain.kb_inventory import inventory
from second_brain.kb_check import check_run, load_manifest
from second_brain.kb_publish import prepare_review, publish
from second_brain.kb_targeting import preflight


class TargetFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        self.export = self.source / 'export.md'
        self.export.write_text('# Home proposal\nHome limit proposed: 10.\nPending owner review.\nOther product: unrelated.\n')
        self.original = self.source / 'mixed.md'
        self.original.write_text('UNAUTHORIZED MIXED ORIGINAL')
        self.config = self.root / 'home/config/project.json'
        self.config.parent.mkdir(parents=True)
        self.save(self.config, {'schema_version':'0.1','project':{'id':'home','name':'Home','description':'Synthetic'},
            'sources':[{'id':'notes','type':'requirements','path':str(self.source),'include':['**/*'],'exclude':[]}],
            'global_exclude':[], 'knowledge':{'path':'knowledge','approved':'knowledge/approved'},'runs':{'path':'runs'}})
        self.registry_path = self.root / 'registry.json'
        self.registry = {'schema_version':'1.1','projects':[{'id':'home','name':'Home','aliases':[],
            'information_domain':'synthetic','owns_paths':[]}], 'disclosures':[]}
        self.save(self.registry_path, self.registry)
        self.request = {'schema_version':'1.0','project_id':'home','purpose':'analysis_only',
            'capture_mode':'scoped_export','authorized_by':'Synthetic operator','authorized_at':utc_now(),
            'permission_reason':'Synthetic test only', 'selection':[{'source_id':'notes','relative_path':'export.md',
            'sha256':sha(self.export.read_bytes()), 'provenance':{'original_reference':str(self.original),
            'locator':'reviewed excerpt','reviewed_by':'Synthetic reviewer','reviewed_at':utc_now(),'limitations':[]}}],
            'packets':{'composition':'union','globs':[], 'terms':[], 'ranges':[], 'max_chars':16000},
            'registry_path':str(self.registry_path),'context':None}

    def save(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def capture(self, name='one', **kwargs):
        return inventory(self.config, name, request=self.request, **kwargs)


class TargetCaptureTests(TargetFixture):
    def test_strict_capture_and_preflight_never_read_excluded_original(self):
        from second_brain import kb_inventory, kb_targeting
        actual = kb_inventory.read_stable
        reads = []
        def spy(path, limit):
            reads.append(path)
            self.assertNotEqual(path, self.original)
            return actual(path, limit)
        with patch.object(kb_inventory, 'read_stable', side_effect=spy), patch.object(kb_targeting, 'read_stable', side_effect=spy):
            result = preflight(self.config, self.request)
            self.assertEqual(reads, [])
            run, manifest = self.capture()
        self.assertEqual([f['relative_path'] for f in manifest['files']], ['export.md'])
        self.assertNotIn(self.original, reads)
        self.assertEqual(load_manifest(run), manifest)
        self.assertEqual(check_run(run)['status'], 'passed')
        self.assertIn('excluded', result['exclusions'])

    def test_changed_export_hash_blocks_and_missing_or_widened_inputs_fail(self):
        self.export.write_text('Different bytes')
        run, m = self.capture()
        self.assertEqual(m['status'], 'blocked')
        self.assertIn('authorized export hash', str(m['issues']))
        self.export.unlink()
        with self.assertRaisesRegex(KBError, 'missing'):
            self.capture('missing')
        self.request['selection'][0]['relative_path'] = '../outside.md'
        with self.assertRaises(KBError):
            preflight(self.config, self.request)

    def test_edits_comparable_but_policy_changes_incomparable(self):
        first, _ = self.capture()
        self.export.write_text(self.export.read_text() + 'New proposed fact.\n')
        self.request['selection'][0]['sha256'] = sha(self.export.read_bytes())
        second, m = self.capture('two', baseline=first)
        self.assertTrue(m['delta']['compatible'])
        self.assertEqual(len(m['delta']['modified']), 1)
        self.request['packets']['composition'] = 'intersection'
        _, changed = self.capture('three', baseline=second)
        self.assertFalse(changed['delta']['compatible'])
        self.assertEqual(changed['delta']['removed'], [])
        self.assertEqual(load_manifest(first)['status'], 'ready')

    def test_analysis_only_rejected_by_direct_review_and_publish(self):
        run, _ = self.capture()
        with self.assertRaisesRegex(KBError, 'analysis_only'):
            prepare_review(self.config, run)
        with self.assertRaisesRegex(KBError, 'analysis_only'):
            publish(self.config, run, run/'absent.json', human_approved=True)

    def test_whole_file_mode_discloses_storage_and_selected_only_symlinks(self):
        self.request['capture_mode']='whole_file'
        self.request['selection'][0].update(sha256=None, provenance=None)
        self.assertIn('unrelated', preflight(self.config, self.request)['retained_content'])
        (self.source/'excluded-link.md').symlink_to(self.original)
        run, m = self.capture()
        self.assertEqual(m['status'], 'ready')
        self.assertEqual(load_manifest(run), m)


class TargetPassageTests(TargetFixture):
    def prepare_candidate(self, purpose='analysis_only', selected_end=3):
        from second_brain.kb_packet import build_packets
        from second_brain.kb_mentions import scan_mentions
        self.request['purpose'] = purpose
        self.request['packets']['ranges'] = [{'source_id':'notes','relative_path':'export.md','start_line':1,'end_line':selected_end}]
        run, m = self.capture()
        index = build_packets(run)
        scan = scan_mentions(run, self.registry_path)
        data = read_json(run/'packets/coverage-stub.json')
        file = m['files'][0]
        segment = read_json(run/'segments.snapshot.json')['segments'][0]
        cite = {'evidence_id':file['evidence_id'],'segment_id':segment['segment_id'],
            'representation_sha256':segment['representation_sha256'],'start_line':1,'end_line':3,
            'quote':'\n'.join(self.export.read_text().splitlines()[:3])}
        data['records'] = [{'id':'REQ-001','kind':'requirement','title':'Home limit proposal',
            'statement':'The home limit is proposed and pending review.','epistemic_status':'proposal',
            'evidence':[cite],'relations':[], 'open_questions':[], 'investigation':None,'events':[],
            'cross_project':[], 'aliases':[], 'assertions':[],
            'attribution':[{'evidence_ref':0,'class':'home','project_id':'home','reason':'Explicit Home heading.'}]}]
        data['coverage'][0]['disposition']='used'
        data['segment_coverage'][0]['disposition']='used'
        data['interval_coverage'][0]['disposition']='used'
        self.save(run/'proposals/records.json',data)
        referrals = {'schema_version':'1.1','project_id':'home','run_id':'one','registry_sha256':json_sha(self.registry),
            'mentions_sha256':sha((run/'work/mentions.json').read_bytes()),'assessments':[], 'referrals':[], 'manual_mentions':[]}
        self.save(run/'proposals/referrals.json', referrals)
        return run,m,data,index,referrals

    def test_selected_passages_preserve_qualifiers_and_complements(self):
        run,m,data,index,_ = self.prepare_candidate()
        text = (run/index['packets'][0]['path']).read_text()
        self.assertIn('Pending owner review.',text)
        self.assertIn('# Home proposal',text)
        self.assertNotIn('Other product: unrelated.',text)
        self.assertEqual(index['packets'][0]['start_line'],1)
        self.assertEqual(index['packets'][0]['end_line'],3)
        self.assertEqual(data['interval_coverage'][1]['disposition'],'triaged_out')
        self.assertEqual(check_run(run,run/'proposals/records.json',stage2=True)['interval_coverage_count'],2)

    def test_no_alias_hits_still_cannot_evade_targeted_contract(self):
        run,m,data,_,_ = self.prepare_candidate()
        data['schema_version']='0.5'
        del data['interval_coverage']
        for r in data['records']:
            for k in ('attribution','aliases','assertions'): del r[k]
        self.save(run/'proposals/records.json',data)
        with self.assertRaisesRegex(KBError, 'cannot bypass'):
            check_run(run,run/'proposals/records.json')

    def test_gaps_overlaps_unread_citations_and_unknown_attribution_block(self):
        run,m,data,_,_ = self.prepare_candidate()
        for mutation in ('gap','overlap','unread','unknown','R2'):
            bad=copy.deepcopy(data)
            if mutation=='gap': bad['interval_coverage'].pop()
            if mutation=='overlap': bad['interval_coverage'][1]['start_line']=3
            if mutation=='unread': bad['interval_coverage'][0]['disposition']='reviewed_no_record'
            if mutation in ('unknown','R2'):
                bad['records'][0]['epistemic_status']='observed'
                bad['records'][0]['attribution'][0]['class']=mutation
            self.save(run/'proposals/records.json',bad)
            with self.subTest(mutation=mutation), self.assertRaises(KBError):
                check_run(run,run/'proposals/records.json',stage2=True)

    def test_union_intersection_and_empty_are_explicit(self):
        from second_brain.kb_packet import select_evidence, build_packets
        run,m=self.capture()
        eid=m['files'][0]['evidence_id']
        self.assertEqual(select_evidence(run,m,globs=['*.md'],terms=['absent'],composition='union')[0],{eid})
        self.assertEqual(select_evidence(run,m,globs=['*.md'],terms=['absent'],composition='intersection')[0],set())
        self.request['packets'].update(globs=['*.md'],terms=['absent'],composition='intersection')
        empty,_=self.capture('empty')
        with self.assertRaisesRegex(KBError,'empty'):
            build_packets(empty)

    def test_manual_implicit_target_only_reference_blocks_home_record(self):
        self.registry['projects'].append({'id':'other','name':'OtherRegistered','aliases':[],
            'information_domain':'synthetic','owns_paths':[]})
        self.save(self.registry_path,self.registry)
        run,m,data,index,referrals=self.prepare_candidate()
        source=data['records'][0]['evidence'][0]
        manual={'target_project_id':'other','source':source,'reason':'Manual interpretation of an implicit reference.'}
        mid='M-'+json_sha(['manual',source,'other'])[:24]
        referrals['manual_mentions']=[manual]
        referrals['assessments']=[{'mention_id':mid,'class':'R2','disposition':'unresolved','reason':'Target only',
            'home_record_ids':[], 'referral_id':None}]
        self.save(run/'proposals/referrals.json',referrals)
        with self.assertRaisesRegex(KBError,'R2 target-only'):
            check_run(run,run/'proposals/records.json')

    def referred_candidate(self, selected_end=3):
        self.registry['projects'].append({'id':'other','name':'OtherRegistered','aliases':[],
            'information_domain':'synthetic','owns_paths':[]})
        self.registry['disclosures'].append({'from_project':'home','to_project':'other',
            'source_id':'notes','path_pattern':'export.md'})
        self.save(self.registry_path,self.registry)
        run,m,data,index,referrals=self.prepare_candidate('project_refresh',selected_end)
        source=copy.deepcopy(data['records'][0]['evidence'][0])
        mid='M-'+json_sha(['manual',source,'other'])[:24]
        referrals['manual_mentions']=[{'target_project_id':'other','source':source,'reason':'Synthetic shared component.'}]
        referrals['assessments']=[{'mention_id':mid,'class':'R4','disposition':'referred','reason':'Synthetic routing.',
            'home_record_ids':['REQ-001'],'referral_id':'REF-001'}]
        referrals['referrals']=[{'id':'REF-001','target_project_id':'other','class':'R4','source':copy.deepcopy(source),
            'summary':'Synthetic proposal.','why_target_cares':'Synthetic shared limit.','home_record_ids':['REQ-001'],
            'suggested_capture':{'source_id':'notes','relative_path':'export.md','include_pattern':'export.md'},
            'disposition':'pending_target_review'}]
        data['records'][0]['cross_project']=[{'project_id':'other','reason':'Synthetic shared component.','target_record':None}]
        data['records'][0]['attribution'][0].update({'class':'R4','project_id':'other'})
        self.save(run/'proposals/records.json',data)
        self.save(run/'proposals/referrals.json',referrals)
        return run,data,referrals

    def test_check_run_referral_crossing_unselected_complement_is_rejected(self):
        run,data,referrals=self.referred_candidate()
        self.assertEqual(check_run(run,run/'proposals/records.json',stage2=True)['referral_count'],1)
        referrals['referrals'][0]['source'].update(end_line=4,quote='\n'.join(self.export.read_text().splitlines()))
        self.save(run/'proposals/referrals.json',referrals)
        with self.assertRaisesRegex(KBError,'selected passages'):
            check_run(run,run/'proposals/records.json',stage2=True)

    def test_check_run_referral_crossing_selected_unread_interval_is_rejected(self):
        run,data,referrals=self.referred_candidate(selected_end=4)
        row=data['interval_coverage'][0]
        data['interval_coverage']=[dict(row,end_line=3),
            dict(row,start_line=4,disposition='triaged_out',method='manual_triage',note='Selected but not read.')]
        self.save(run/'proposals/records.json',data)
        self.assertEqual(check_run(run,run/'proposals/records.json',stage2=True)['referral_count'],1)
        referrals['referrals'][0]['source'].update(end_line=4,quote='\n'.join(self.export.read_text().splitlines()))
        self.save(run/'proposals/referrals.json',referrals)
        with self.assertRaisesRegex(KBError,'unread interval'):
            check_run(run,run/'proposals/records.json',stage2=True)
        data['interval_coverage'][1]['disposition']='reviewed_no_record'
        del data['interval_coverage'][1]['method']
        self.save(run/'proposals/records.json',data)
        self.assertEqual(check_run(run,run/'proposals/records.json',stage2=True)['referral_count'],1)

    def test_refresh_review_exposes_and_binds_unread_intervals(self):
        run,m,data,index,referrals=self.prepare_candidate('project_refresh')
        review=prepare_review(self.config,run)
        self.assertEqual(review['schema_version'],'0.4')
        self.assertEqual(review['triaged_segment_ids'],[data['segment_coverage'][0]['segment_id']])
        self.assertIn('Unread interval',(run/'review-report.md').read_text())

    def test_unselected_unavailable_source_does_not_block_exact_membership(self):
        cfg=read_json(self.config)
        cfg['sources'].append({'id':'excluded','type':'repository','path':str(self.root/'unavailable'),
            'include':['**/*'],'exclude':[]})
        self.save(self.config,cfg)
        run,m=self.capture()
        self.assertEqual(m['status'],'ready')
        self.assertTrue(any(i['code']=='unselected_source_scope' for i in m['issues']))
        self.assertEqual(check_run(run)['status'],'passed')

    def test_legacy_packet_whole_segment_and_exact_range_selection(self):
        from second_brain.kb_inventory import inventory
        from second_brain.kb_packet import build_packets
        run,m=inventory(self.config,'legacy')
        file=next(f for f in m['files'] if f['relative_path']=='export.md')
        segment=next(s for s in read_json(run/'segments.snapshot.json')['segments'] if s['evidence_id']==file['evidence_id'])
        index=build_packets(run,segment_ids=[segment['segment_id']])
        self.assertEqual(index['selected_evidence_ids'],[file['evidence_id']])
        self.assertIn('Other product',(run/index['packets'][0]['path']).read_text())
        ranged,m2=inventory(self.config,'ranges')
        file2=next(f for f in m2['files'] if f['relative_path']=='export.md')
        index2=build_packets(ranged,ranges=[{'evidence_id':file2['evidence_id'],'start_line':1,'end_line':3}])
        self.assertNotIn('Other product',(ranged/index2['packets'][0]['path']).read_text())
        self.assertEqual(index2['packets'][0]['end_line'],3)

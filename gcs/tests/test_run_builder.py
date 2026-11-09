"""Ordered instances, atomic publication and page-session isolation."""
from copy import deepcopy
import itertools
import json
import tempfile
from pathlib import Path
import unittest
from test_competition_run import CompetitionRunTests
from gcs.app.run_builder import generate_run
from gcs.app.sessions import SessionWorkspace
from shared.run_builder import validate_run


def fixture():
    m, old, gps = CompetitionRunTests().fixture()
    old['task_setup']['slalom']['passages'] = old['task_setup']['slalom']['passages'][1:]
    settings = {**old['settings'], 'tower_avoidance': {'hard_m': .5, 'soft_m': .5, 'strength': 0, 'overrides': {}}}
    run = {'planning_mode': 'run', 'steps': [{'id': t, 'type': t, 'setup': s} for t,s in old['task_setup'].items()],
           'settings': settings, 'planning_area': old['planning_area'], 'start': old['start'], 'sizes_confirmed': True,
           'attempt': {'mode': 'full', 'start_source': 'manual'}, 'shared_crossings': [], 'execution_budget_s': 500}
    return m, run, gps


class RunBuilderTests(unittest.TestCase):
    def test_permutations_repeats_manual_and_channel_before_another_card(self):
        m, run, gps = fixture()
        setups = {s['type']:s['setup'] for s in run['steps']}
        setups['manual'] = {'course_confirmed': True, 'waypoints': [gps(-5,0),gps(-4,0)], 'finish_radius_m': 1}
        for types in [*itertools.permutations(('gate','slalom')), ('gate','gate'), ('manual',), ('manual','gate'), ('channel','manual')]:
            d = deepcopy(run)
            # A nearby manual endpoint after Channel avoids a costly unrelated
            # full-course return search in this focused geometry regression.
            if types == ('channel','manual'):
                setups['manual'] = {'course_confirmed': True, 'waypoints': [gps(49,0)]}
            d['steps'] = [{'id':str(i), 'type':t, 'setup':setups[t]} for i,t in enumerate(types)]
            result = generate_run(m,d,max_seconds=20)
            self.assertTrue(result['success'], (types,result))
            out = result['draft']
            self.assertTrue(validate_run(m,out)['valid'])
            self.assertEqual([b['instance_id'] for b in out['blocks']], [str(i) for i in range(len(types))])
            self.assertTrue(out['blocks'][-1]['stopped_finish'])
            self.assertFalse(any(b['stopped_finish'] for b in out['blocks'][:-1]))
            for b in out['blocks']:
                if b['type'] == 'manual':
                    self.assertEqual(out['waypoints'][b['waypoint_start']:b['waypoint_end']],setups['manual']['waypoints'])

    def test_gate_and_slalom_are_separate_blocks_without_a_return_crossing(self):
        m,r,_ = fixture()
        r['steps'] = r['steps'][:2]
        result = generate_run(m,r,max_seconds=15)
        self.assertTrue(result['success'], result)
        out = result['draft']
        self.assertEqual([b['instances'] for b in out['blocks']], [['gate'], ['slalom']])
        self.assertTrue(validate_run(m,out)['valid'])
        from shared.geometry import to_local
        slalom = out['blocks'][1]
        points = out['waypoints'][slalom['waypoint_start']-1:slalom['waypoint_end']]
        self.assertTrue(all(to_local(p,m['geographic_reference'])[0] > 0 for p in points))
        # Old shared-crossing requests and merged blocks cannot skip Gate.
        d = deepcopy(r);d['shared_crossings'] = [{'gate_id':'gate','slalom_id':'slalom','signature':'old'}]
        self.assertFalse(generate_run(m,d)['success'])
        d = deepcopy(out);d['blocks'][0]['instances'] = ['gate','slalom']
        self.assertFalse(validate_run(m,d)['valid'])

    def test_standalone_slalom_keeps_every_turn_and_exit_but_no_starting_gate(self):
        m,r,gps = fixture()
        r['steps'] = [r['steps'][1]]
        r['start'] = gps(4,0)
        result = generate_run(m,r,max_seconds=15)
        self.assertTrue(result['success'],result)
        out = result['draft']
        self.assertTrue(validate_run(m,out)['valid'])
        self.assertEqual([b['instances'] for b in out['blocks']], [['slalom']])
        self.assertEqual([p['id'] for p in out['steps'][0]['setup']['passages']], ['turn','exit'])
        broken = deepcopy(out)
        # A route stopping before the exit must still fail course validation.
        broken['waypoints'][-1] = gps(12,0)
        self.assertFalse(validate_run(m,broken)['valid'])
        r['steps'][0]['setup']['passages'].insert(0,{'id':'entrance','kind':'gate','red':'a','green':'b'})
        stale = generate_run(m,r)
        self.assertFalse(stale['success'])
        self.assertIn('separate Gate card',stale['diagnostics'][0])

    def test_deadline_blocked_joins_overflow_duplicate_ids_and_no_partial(self):
        m,r,gps = fixture()
        self.assertFalse(generate_run(m,r,max_seconds=0)['success'])
        d = deepcopy(r);d['steps'][1]['id'] = d['steps'][0]['id']
        self.assertFalse(generate_run(m,d)['success'])
        d = deepcopy(r);d['steps'] = [{'id':'many','type':'manual','setup':{'course_confirmed':True,'waypoints':[gps(-4,0)]*501}}]
        out = generate_run(m,d);self.assertFalse(out['success']);self.assertNotIn('draft',out)
        d = deepcopy(r);d['steps'] = [{'id':'blocked','type':'manual','setup':{'course_confirmed':True,'waypoints':[gps(0,5),gps(4,0)]}}]
        self.assertFalse(generate_run(m,d)['success'])

    def test_sessions_never_restore_or_touch_old_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'workspace.json';path.write_text('{"map":"old","approval":"old"}')
            before = path.read_bytes()
            a,b = SessionWorkspace(),SessionWorkspace()
            m,r,_ = fixture();a.edit({'revision':0,'map':m,'new_import':True})
            a.edit({'revision':1,'run_draft':r})
            self.assertIsNone(b.read()['map']);self.assertIsNone(SessionWorkspace().read()['map'])
            self.assertEqual(path.read_bytes(),before)
            a.reset();self.assertIsNone(a.read()['map']);self.assertIsNone(a.read()['return_target'])

    def test_reused_ids_import_defaults_and_delayed_generation(self):
        w = SessionWorkspace();m,r,_ = fixture()
        w.edit({'revision':0,'map':m,'new_import':True});w.edit({'revision':1,'run_draft':r})
        snapshot,token = w.begin_generation()
        out = generate_run(m,snapshot['run_draft'],max_seconds=15)
        self.assertTrue(out['success'],out)
        changed = deepcopy(m);changed['buoys'][0]['centre']['latitude'] += .0001
        w.edit({'revision':snapshot['revision'],'map':changed,'new_import':True})
        with self.assertRaisesRegex(ValueError,'Superseded'):w.publish(out['draft'],token)
        state = w.read();self.assertFalse(state['run_draft']['steps']);self.assertFalse(state['run_draft']['waypoints'])
        self.assertEqual(state['run_draft']['settings']['speed_m_s'],.5)
        self.assertEqual(state['run_draft']['settings']['clearance_m'],1.8)
        with self.assertRaises(ValueError):w.edit({'revision':0,'run_draft':r})

    def test_client_cannot_restore_generated_geometry_and_stop_invalidates_pending(self):
        w = SessionWorkspace();m,r,_ = fixture()
        w.edit({'revision':0,'map':m,'new_import':True});w.edit({'revision':1,'run_draft':r})
        snapshot,token = w.begin_generation();out = generate_run(m,snapshot['run_draft'],max_seconds=15)
        w.consume_run()
        with self.assertRaises(ValueError):w.publish(out['draft'],token)
        w.edit({'revision':w.read()['revision'],'run_draft':out['draft']})
        self.assertFalse(w.read()['run_draft']['waypoints'])
        with self.assertRaises(ValueError):w.approve()

    def test_repeated_return_uses_current_reviewed_inputs_and_revokes_changed_map(self):
        from gcs.app.sessions import return_inputs
        w=SessionWorkspace();m,r,gps=fixture()
        w.edit({'revision':0,'map':m,'new_import':True})
        changed=deepcopy(r);changed['planning_area'][0]=gps(-13,-15)
        w.edit({'revision':1,'run_draft':changed})
        _,token=w.begin_generation()
        returned={'planning_mode':'return','settings':deepcopy(r['settings']),'waypoints':[r['start']]}
        w.publish(returned,token)
        current=return_inputs(w.read())
        self.assertEqual(current['planning_area'],changed['planning_area'])
        self.assertFalse(current['waypoints'])
        self.assertEqual(current['steps'],changed['steps'])
        altered=deepcopy(m);altered['buoys'][0]['centre']=gps(1,-5)
        w.edit({'revision':w.read()['revision'],'map':altered})
        current=return_inputs(w.read())
        self.assertFalse(current['sizes_confirmed'])
        self.assertTrue(all(not s['setup']['course_confirmed'] for s in current['steps']))


if __name__ == '__main__':unittest.main()

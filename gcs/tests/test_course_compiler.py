"""Recognition uses physical relationships, never row order or course IDs."""
from copy import deepcopy
import json
import math
from pathlib import Path
import random
import unittest
from gcs.app.course_compiler import compile_course, huber, validate_assignments
from gcs.app.course_profile import SLALOM, CHANNEL
from shared.geometry import to_local, to_gps


def competition():
    return json.loads((Path(__file__).resolve().parents[1]/'examples/competition-gps-map.json').read_text())


class CompilerTests(unittest.TestCase):
    def test_compact_slalom_does_not_pair_opposite_ends(self):
        m = competition()
        m['buoys'] = [o for o in m['buoys'] if o['id'].startswith('dodge')]
        m['obstacles'] = []
        positions = {
            'dodge_gate_a_red': (27, 2), 'dodge_gate_a_green': (27, -2),
            'dodge_turn_1': (23, 0), 'dodge_turn_2': (18, 0),
            'dodge_turn_3': (11, 0), 'dodge_turn_4': (5, 0),
            'dodge_gate_b_red': (0, 2), 'dodge_gate_b_green': (0, -2),
        }
        self.assertEqual({o['id'] for o in m['buoys']}, set(positions))
        for obj in m['buoys']:
            obj['centre'] = to_gps(*positions[obj['id']], m['geographic_reference'])
        result = compile_course(m)
        expected = dict(zip(SLALOM, (
            'dodge_gate_a_red', 'dodge_gate_a_green',
            'dodge_turn_1', 'dodge_turn_2', 'dodge_turn_3', 'dodge_turn_4',
            'dodge_gate_b_red', 'dodge_gate_b_green')))
        self.assertTrue(any(c['tasks'].get('slalom') == expected
                            for c in result['candidates']))
        self.assertEqual(result['candidates'][0]['tasks']['slalom'], expected)
        for candidate in result['candidates']:
            validate_assignments(m, candidate['tasks'])
            roles = candidate['tasks'].get('slalom', {})
            self.assertNotEqual(
                {roles.get(SLALOM[0]), roles.get(SLALOM[1])},
                {'dodge_gate_b_red', 'dodge_gate_a_green'})

    def test_gate_segments_cannot_cross_each_other_or_interior_progression(self):
        m = competition()
        roles = dict(zip(SLALOM, (
            'dodge_gate_a_red', 'dodge_gate_a_green',
            'dodge_turn_1', 'dodge_turn_2', 'dodge_turn_3', 'dodge_turn_4',
            'dodge_gate_b_red', 'dodge_gate_b_green')))
        for entrance, exit, message in (
                (((0, 2), (27, -2)), ((27, 2), (0, -2)), 'gates cross'),
                (((13, 5), (13, -5)), ((0, 2), (0, -2)), 'interior progression'),
                (((27, 2), (27, -2)), ((13, 5), (13, -5)), 'interior progression')):
            positions = [*entrance, (23, 0), (18, 0), (11, 0), (5, 0), *exit]
            by_id = dict(zip(roles.values(), positions))
            for obj in m['buoys']:
                if obj['id'] in by_id:
                    obj['centre'] = to_gps(*by_id[obj['id']], m['geographic_reference'])
            with self.assertRaisesRegex(ValueError, message):
                validate_assignments(m, {'slalom': roles})

    def test_measured_uneven_practice_layout_ranks_local_progression_first(self):
        # Relative measured geometry only; private GPS and observation IDs are
        # excluded. Rotations and input ordering must not change the assignment.
        positions = [(0, 0), (-.211882, 4.308064), (4.559709, 2.137334),
                     (10.602595, 1.714320), (17.391306, 1.803376),
                     (22.518860, 1.870167), (26.264944, -.244903),
                     (26.628542, 3.870788)]
        for angle in (0, .7, 2.3):
            m = competition()
            m['obstacles'] = []
            m['buoys'] = [dict(id=f'obs_{i}', type='point', object_type='buoy',
                               category='green' if i % 2 == 0 else 'red',
                               centre=to_gps(math.cos(angle)*x-math.sin(angle)*y,
                                             math.sin(angle)*x+math.cos(angle)*y,
                                             m['geographic_reference']))
                          for i, (x, y) in enumerate(positions)]
            random.Random(17).shuffle(m['buoys'])
            before = deepcopy(m)
            roles = compile_course(m)['candidates'][0]['tasks']['slalom']
            self.assertEqual([roles[r] for r in SLALOM],
                             ['obs_7', 'obs_6', 'obs_5', 'obs_4',
                              'obs_3', 'obs_2', 'obs_1', 'obs_0'])
            self.assertEqual(m, before)

    def test_full_map_and_identity_independence(self):
        m = competition()
        before = deepcopy(m)
        result = compile_course(m)
        self.assertEqual(m, before)
        top = result['candidates'][0]
        self.assertEqual(top['tasks']['slalom']['slalom.turn.1'], 'dodge_turn_1')
        self.assertEqual(top['tasks']['channel']['channel.red.1'], 'evade_left_0')
        self.assertEqual(top['tasks']['gate'], {k:top['tasks']['slalom'][k] for k in SLALOM[:2]})
        original = {o['id']:o['centre'] for o in m['buoys']}
        rng = random.Random(415)
        rng.shuffle(m['buoys'])
        replacements = {}
        for i, obj in enumerate(m['buoys']):
            replacements[obj['id']] = f'opaque_{i}'
            obj['id'] = f'opaque_{i}'
            obj.pop('task', None)
        other = compile_course(m)['candidates'][0]
        self.assertEqual(other['tasks'], {t:{r:replacements[k] for r,k in roles.items()} for t,roles in top['tasks'].items()})
        self.assertEqual(original['dodge_turn_1'], next(o for o in m['buoys'] if o['id']==replacements['dodge_turn_1'])['centre'])
        self.assertLessEqual(result['elapsed_s'], 5.1)
        self.assertLessEqual(result['expanded_states'], 200000)
        self.assertTrue(result['search_exhausted'])
        self.assertGreater(len(result['candidates']), 1)

    def test_rotated_curved_skewed_uneven_and_arbitrary_connection(self):
        for angle in (.43, 2.12, 4.68):
            m = competition()
            for obj in m['buoys']+m['obstacles']:
                x,y = to_local(obj['centre'],m['geographic_reference'])
                if obj['id'].startswith('dodge'):
                    y += .0018*(x+10.72)**2
                    if 'turn' in obj['id']:
                        y += .6 if obj['category']=='red' else -.6
                    if 'gate_b_red' in obj['id']:
                        x += 1.1
                if obj['id'].startswith('evade'):
                    # Rotate channel about its entry independently of slalom.
                    u,v=x+67.1,y
                    x,y=-67.1+math.cos(.5)*u-math.sin(.5)*v,math.sin(.5)*u+math.cos(.5)*v
                    if obj['category']=='green':x+=.5*(-v)/9.144
                obj['centre']=to_gps(math.cos(angle)*x-math.sin(angle)*y, math.sin(angle)*x+math.cos(angle)*y,m['geographic_reference'])
            result=compile_course(m)
            self.assertTrue(any(c['tasks'].get('slalom',{}).get('slalom.turn.1')=='dodge_turn_1' and set(c['tasks'].get('channel',{}).values())=={o['id'] for o in m['buoys'] if o['id'].startswith('evade')} for c in result['candidates']),result)

    def test_missing_detections_retain_gate_and_channel(self):
        m=competition()
        m['buoys']=[o for o in m['buoys'] if not o['id'].startswith('dodge_turn')]
        result=compile_course(m)
        self.assertTrue(any('gate' in c['tasks'] and 'channel' in c['tasks'] and 'slalom' in c['unresolved'] for c in result['candidates']))
        self.assertTrue(result['partials']['slalom'])

    def test_types_hints_and_structural_contradictions(self):
        m=competition()
        top=compile_course(m)['candidates'][0]['tasks']
        validate_assignments(m,top)
        with self.assertRaisesRegex(ValueError,'reuse'):
            compile_course(m,{'slalom.turn.1':'dodge_turn_1','channel.red.1':'dodge_turn_1'})
        with self.assertRaisesRegex(ValueError,'color'):
            compile_course(m,{'slalom.turn.1':'dodge_turn_2'})
        with self.assertRaises(ValueError):
            compile_course(m,{'bad':'dodge_turn_1'})
        swapped=deepcopy(top)
        swapped['channel']['channel.green.2'],swapped['channel']['channel.green.3']=swapped['channel']['channel.green.3'],swapped['channel']['channel.green.2']
        with self.assertRaises(ValueError):validate_assignments(m,swapped)
        for o in m['buoys']:o['object_type']='unknown'
        self.assertFalse(compile_course(m)['candidates'])

    def test_extra_competing_patterns_and_pins(self):
        m=competition()
        extras=[]
        for obj in m['buoys']:
            if obj.get('category') in ('red','green'):
                other=deepcopy(obj);other['id']='extra_'+obj['id']
                x,y=to_local(other['centre'],m['geographic_reference']);other['centre']=to_gps(x,y+65,m['geographic_reference']);extras.append(other)
        m['buoys']+=extras
        result=compile_course(m)
        self.assertGreater(len(result['candidates']),1)
        for c in result['candidates']:validate_assignments(m,c['tasks'])
        pinned=compile_course(m,{'slalom.turn.1':'extra_dodge_turn_1'})
        self.assertTrue(any(c['tasks'].get('slalom',{}).get('slalom.turn.1')=='extra_dodge_turn_1' for c in pinned['candidates']))

    def test_bounds_and_huber(self):
        self.assertEqual(huber(.5),.125);self.assertEqual(huber(-2),1.5)
        for bounds in ({'max_states':0},{'max_seconds':0}):
            result=compile_course(competition(),**bounds)
            self.assertTrue(result['search_exhausted']);self.assertEqual(result['status'],'unresolved')
        result=compile_course(competition(),max_states=25)
        self.assertLessEqual(result['expanded_states'],25)
        self.assertTrue(result['search_exhausted'])

    def test_navigation_type_does_not_depend_on_original_map_collection(self):
        m=competition();top=compile_course(m)['candidates'][0]['tasks']
        obj=next(o for o in m['buoys'] if o['id']=='dodge_turn_1')
        m['buoys'].remove(obj);m['obstacles'].append(obj)
        other=compile_course(m)['candidates'][0]['tasks']
        self.assertEqual(other,top)
        validate_assignments(m,other)

    def test_unspecified_gate_width_and_tower_counts(self):
        for width,count in ((2.,0),(7.,1),(8.,3)):
            m=competition()
            for obj in m['buoys']:
                if obj['id'].startswith('dodge_gate'):
                    x,y=to_local(obj['centre'],m['geographic_reference'])
                    obj['centre']=to_gps(x,math.copysign(width/2,y),m['geographic_reference'])
            towers=[o for o in m['obstacles'] if o.get('object_type')=='detector']
            m['obstacles']=[o for o in m['obstacles'] if o not in towers]
            for i in range(count):
                obj=deepcopy(towers[i%2]);obj['id']='tower_'+str(i);m['obstacles'].append(obj)
            pins={r:k for r,k in compile_course(competition())['candidates'][0]['tasks']['slalom'].items()}
            result=compile_course(m,pins)
            self.assertTrue(any('slalom' in c['tasks'] and 'channel' in c['tasks'] for c in result['candidates']))
            self.assertTrue(any(abs(measure['actual_m']-width)<1e-5 for measure in result['candidates'][0]['details']['slalom']['measurements'] if 'width' in measure['label']))

    def test_bending_channel_and_one_missing_observation(self):
        m=competition()
        for obj in m['buoys']:
            if obj['id'] in ('evade_left_1','evade_right_1'):
                x,y=to_local(obj['centre'],m['geographic_reference']);obj['centre']=to_gps(x+1.7,y-.7,m['geographic_reference'])
        result=compile_course(m)
        self.assertEqual(set(result['candidates'][0]['tasks']['channel'].values()),{o['id'] for o in m['buoys'] if o['id'].startswith('evade')})
        m['buoys']=[o for o in m['buoys'] if o['id']!='dodge_turn_3']
        result=compile_course(m)
        self.assertTrue(all(c['unresolved'] for c in result['candidates']))
        self.assertTrue(any('channel' in c['tasks'] for c in result['candidates']))


if __name__=='__main__':unittest.main()

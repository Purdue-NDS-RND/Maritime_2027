"""Compact measured layout: continuous crossings and fresh full-task approaches."""
from copy import deepcopy
import math
import time
import unittest
from gcs.app.course_setup import prepare_task
from gcs.app.planner import generate
from gcs.app.run_builder import generate_run
from gcs.app.settings import defaults, effective_settings
from shared.clearance import validate_route
from shared.course import Course, dot, sub
from shared.geometry import to_gps, to_local
from shared.run_builder import task_input, validate_run


def compact_course(angle=0):
    # Relative measurements only: no private survey GPS or observation IDs.
    positions = [(0, 0), (-.211882, 4.308064), (4.559709, 2.137334),
                 (10.602595, 1.714320), (17.391306, 1.803376),
                 (22.518860, 1.870167), (26.264944, -.244903),
                 (26.628542, 3.870788)]
    ref = {'latitude': 51.5, 'longitude': -4}
    def gps(x, y):
        return to_gps(7+x*math.cos(angle)-y*math.sin(angle),
                      -9+x*math.sin(angle)+y*math.cos(angle), ref)
    m = {'schema_version': 3, 'source': 'live', 'geographic_reference': ref,
         'buoys': [dict(id=f'p{i+1}', type='point', object_type='buoy',
                        category='green' if i % 2 == 0 else 'red', centre=gps(x, y))
                   for i, (x, y) in enumerate(positions)], 'obstacles': []}
    roles = {'slalom.entrance.red': 'p8', 'slalom.entrance.green': 'p7',
             'slalom.exit.red': 'p2', 'slalom.exit.green': 'p1',
             **{f'slalom.turn.{i}': f'p{7-i}' for i in range(1, 5)}}
    steps = []
    for task in ('gate', 'slalom'):
        d = prepare_task(m, task, assignments=roles)['draft']
        d['course_confirmed'] = True
        steps.append({'id': task, 'type': task, 'setup': d})
    r = {'planning_mode': 'run', 'steps': steps, 'settings': effective_settings(defaults()),
         'planning_area': [gps(x, y) for x, y in [(-10, -10), (40, -10), (40, 15), (-10, 15)]],
         'start': gps(32, 1.8), 'sizes_confirmed': True,
         'attempt': {'mode': 'full', 'start_source': 'manual'}, 'shared_crossings': [],
         'execution_budget_s': 300}
    return m, r, gps


class CompactCourseTests(unittest.TestCase):
    def test_first_turn_allows_return_without_awarding_progress(self):
        for angle in (0, .7, 2.3):
            m, r, _ = compact_course(angle)
            d = task_input(r, r['steps'][1], r['steps'][0]['setup']['finish'], True)
            c = Course(m, d)
            origin, forward, left, low, _, _ = c.planes[0]
            start = to_local(d['start'], c.reference)
            self.assertAlmostEqual(dot(sub(start, origin), forward), .93388, places=4)
            for side in (low+1, -low-1):
                before = tuple(origin[i]-forward[i]+side*left[i] for i in (0, 1))
                after = tuple(origin[i]+forward[i]+side*left[i] for i in (0, 1))
                self.assertEqual(c.edge(after, before, 0), 0)
                if side > 0:
                    self.assertEqual(c.edge(before, after, 0), 1)
                    self.assertIsNone(c.edge(after, before, 1))
                else:
                    self.assertIsNone(c.edge(before, after, 0))
            # Approach permission cannot override obstacle or boundary clearance.
            self.assertIsNone(c.edge(start, origin, 0))
            self.assertEqual(c.initial_progress, 0)

    def test_combined_run_crosses_gate_without_overshooting_first_turn(self):
        for angle in (0, .7, 2.3):
            with self.subTest(angle=angle):
                m, r, _ = compact_course(angle)
                original = deepcopy(r)
                result = generate_run(m, r, max_seconds=5)
                self.assertTrue(result['success'], result)
                out = result['draft']
                self.assertEqual(r, original)
                self.assertTrue(validate_run(m, out)['valid'])
                self.assertEqual(out['settings']['clearance_m'], 1.8)
                self.assertEqual([b['type'] for b in out['blocks']], ['gate', 'slalom'])
                self.assertFalse(out['blocks'][0]['stopped_finish'])
                self.assertTrue(out['blocks'][1]['stopped_finish'])
                end = out['waypoints'][out['blocks'][0]['waypoint_end']-1]
                c = Course(m, task_input(r, r['steps'][1], end, True))
                origin, forward, *_ = c.planes[0]
                self.assertLess(dot(sub(to_local(end, c.reference), origin), forward), 0)
                self.assertEqual(out['finish'], r['steps'][-1]['setup']['finish'])
                self.assertEqual(out['steps'], r['steps'])
                # A client cannot claim a crossing by merely moving block metadata.
                broken = deepcopy(out)
                broken['waypoints'][broken['blocks'][0]['waypoint_end']-1] = r['start']
                self.assertFalse(validate_run(m, broken)['valid'])

    def test_standalone_slalom_returns_from_beyond_first_and_later_turns(self):
        for start in ((21.629796, -1.576308), (14, 6), (3, -4)):
            m, r, gps = compact_course()
            r['steps'] = [r['steps'][1]]
            r['start'] = gps(*start)
            result = generate_run(m, r, max_seconds=5)
            self.assertTrue(result['success'], (start, result))
            out = result['draft']
            self.assertTrue(validate_run(m, out)['valid'])
            block = out['blocks'][0]
            self.assertEqual(block['attempt'].get('initial_progress'), 0)
            self.assertEqual(len(out['steps'][0]['setup']['passages']), 5)
            # A direct shortcut to the finish must not count unvisited turns.
            d = task_input(out, out['steps'][0], out['start'], True)
            d['waypoints'] = [d['finish']]
            self.assertFalse(validate_route(m, d)['valid'])

    def test_intermediate_crossing_ignores_stopping_disk_but_final_gate_keeps_it(self):
        m, r, _ = compact_course()
        r['steps'][0]['setup']['finish'] = deepcopy(m['buoys'][0]['centre'])
        result = generate_run(m, r, max_seconds=5)
        self.assertTrue(result['success'], result)
        self.assertTrue(validate_run(m, result['draft'])['valid'])
        r['steps'] = r['steps'][:1]
        result = generate_run(m, r, max_seconds=1)
        self.assertFalse(result['success'])
        self.assertIn('unsafe finish', result['diagnostics'][0])
        d = task_input(r, r['steps'][0], r['start'], True)
        self.assertFalse(generate(m, d, passage_finish=True)['success'])

    def test_tight_gate_is_rejected_immediately_without_lowering_clearance(self):
        m, r, gps = compact_course()
        m['buoys'][-1]['centre'] = gps(26.264944, 2.755097)
        started = time.monotonic()
        result = generate_run(m, r, max_seconds=5)
        self.assertFalse(result['success'])
        self.assertIn('insufficient gate opening', result['diagnostics'][0])
        self.assertNotIn('draft', result)
        self.assertEqual(r['settings']['clearance_m'], 1.8)
        self.assertLess(time.monotonic()-started, 1)

    def test_search_failure_identifies_next_crossing_without_claiming_blockage(self):
        m, r, _ = compact_course()
        d = task_input(r, r['steps'][1], r['steps'][0]['setup']['finish'], True)
        result = generate(m, d, max_expansions=1)
        self.assertFalse(result['success'])
        self.assertIn('blockage is not proven', result['diagnostics'][0])
        self.assertIn('next required passage: turn_1', result['diagnostics'][0])
        self.assertEqual(result['errors'][0]['passage'], 'turn_1')
        self.assertIsNotNone(result['errors'][0]['location'])
        self.assertTrue(all(a['furthest_progress']==0 for a in result['attempts']))


if __name__ == '__main__':
    unittest.main()

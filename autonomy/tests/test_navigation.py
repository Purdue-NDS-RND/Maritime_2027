"""Mission semantics with shared, persistent map identities."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ros_ws/src/maritime_navigation'))
from maritime_navigation.mission import Landmark, Mission, search_goal


def mapped(mission, buoys, now):
    mission.landmarks = [Landmark(f'buoy-{i}', color, x, y, now, 5)
                         for i, (color, x, y) in enumerate(buoys)]


class CourseTests(unittest.TestCase):
    def test_search_viewpoints_are_local_bounded_and_do_not_advance_course(self):
        mission = Mission()
        mapped(mission, [('red', 7, -2), ('green', 7, 2)], 0.)
        mission.update(0, 0, 0, 0.)
        mission.passed = 1
        events = list(mission.events)
        goals = [search_goal(mission, (15., .5, 0.), [-5, -12, 45, 12], i) for i in range(4)]
        self.assertEqual([g[:2] for g in goals], [(16., -2.), (16., 2.), (17., -2.), (17., 2.)])
        self.assertIsNone(search_goal(mission, (15., .5, 0.), [-5, -12, 45, 12], 4))
        self.assertIsNone(search_goal(mission, (44., .5, 0.), [-5, -12, 45, 12], 0))
        self.assertEqual(mission.events, events)

    def test_missing_expected_turn_color_enters_search(self):
        mission = Mission()
        mapped(mission, [('red', 7, -2), ('green', 7, 2), ('green', 19, 0)], 0.)
        target = mission.update(0, 0, 0, 0.)
        self.assertIsNone(mission.update(*target, 0., 1.))
        self.assertEqual(mission.stage, 'search')
        self.assertEqual(mission.events, ['gate_a'])

    def test_full_course_preserves_order_and_required_sides(self):
        mission = Mission()
        buoys = [('red', 7, -2), ('green', 7, 2), ('red', 13, 0), ('green', 19, 0),
                 ('red', 25, 0), ('green', 31, 0), ('red', 37, -2), ('green', 37, 2)]
        x = y = 0.
        for i in range(20):
            mapped(mission, buoys, float(i))
            target = mission.update(x, y, 0., float(i))
            if target is None:
                break
            if mission.stage.startswith('turn_'):
                active = next(b for b in mission.landmarks if b.identity in mission.active_ids)
                self.assertGreater(target[1]-active.y if active.category == 'red' else active.y-target[1], 1.4)
            x, y = target
        self.assertEqual(mission.stage, 'complete')
        self.assertEqual(mission.events, ['gate_a', 'turn_1', 'turn_2', 'turn_3', 'turn_4', 'gate_b'])
        self.assertGreater(x-1.1, 37.)

    def test_gate_is_relative_to_map_frame(self):
        mission = Mission(turns=0)
        angle = .7
        def transform(x, y):
            return (40+x*math.cos(angle)-y*math.sin(angle),
                    -12+x*math.sin(angle)+y*math.cos(angle))
        mapped(mission, [(c, *transform(7, y)) for c, y in [('red', -2), ('green', 2)]], 0.)
        target = mission.update(40, -12, angle, 0.)
        exit_x = 7+math.hypot(1.1, .6)+.35+.15+.75
        self.assertAlmostEqual(target[0], transform(exit_x, 0)[0])
        self.assertAlmostEqual(target[1], transform(exit_x, 0)[1])
        mission.update(*target, angle, .1)
        self.assertEqual(mission.stage, 'complete')

    def test_missing_or_reversed_gate_cannot_start_course(self):
        for buoys in [[('red', 7, -2)], [('red', 7, 2), ('green', 7, -2)]]:
            mission = Mission()
            mapped(mission, buoys, 0.)
            self.assertIsNone(mission.update(0, 0, 0, 0.))

    def test_retained_confirmed_tracks_remain_usable_through_occlusion(self):
        mission = Mission()
        mapped(mission, [('red', 7, -2), ('green', 7, 2)], 0.)
        self.assertIsNotNone(mission.update(0, 0, 0, 50.))
        self.assertEqual(mission.stage, 'gate_a')
        mission = Mission()
        mapped(mission, [('red', 7, -2), ('green', 7, 2)], 0.)
        for buoy in mission.landmarks:
            buoy.count = 0
        self.assertIsNone(mission.update(0, 0, 0, 50.))

    def test_crossing_target_plane_far_away_does_not_complete(self):
        mission = Mission(turns=0)
        mapped(mission, [('red', 7, -2), ('green', 7, 2)], 0.)
        target = mission.update(0, 0, 0, 0.)
        self.assertEqual(mission.update(10, 6, 0, 1.), target)
        self.assertNotEqual(mission.stage, 'complete')

    def test_repeated_categories_keep_physical_map_ids(self):
        mission = Mission(turns=0)
        mapped(mission, [('red', 7, -2), ('green', 7, 2), ('red', 15, -2)], 0.)
        mission.update(0, 0, 0, 0.)
        self.assertEqual(mission.active_ids, ['buoy-0', 'buoy-1'])

    def test_other_obstacle_categories_are_not_course_turns(self):
        mission = Mission()
        mapped(mission, [('red', 7, -2), ('green', 7, 2), ('blue', 10, 0), ('red', 13, 0)], 0.)
        target = mission.update(0, 0, 0, 0.)
        mission.update(*target, 0., 1.)
        self.assertEqual(mission.active_ids, ['buoy-3'])
        self.assertEqual(mission.stage, 'turn_1')

    def test_committed_gate_follows_map_corrections_and_requires_its_tracks(self):
        mission = Mission(turns=0)
        mapped(mission, [('red', 7, -2), ('green', 7, 2)], 0.)
        mission.update(0, 0, 0, 0.)
        mapped(mission, [('red', 8, -2), ('green', 8, 2)], 1.)
        mission.refresh_target()
        self.assertAlmostEqual(mission.target[0], 8+math.hypot(1.1, .6)+.35+.15+.75)
        mission.landmarks = []
        mission.refresh_target()
        self.assertEqual(mission.stage, 'fault')
        self.assertIsNone(mission.target)

    def test_terminal_gate_accounts_for_range_bias_and_arrival_tolerance(self):
        mission = Mission(turns=0)
        # Map gate is 1 m closer than the independently known physical gate.
        mapped(mission, [('red', 6, -2), ('green', 6, 2)], 0.)
        for buoy in mission.landmarks:
            buoy.covariance = (.25**2, 0., 0., .1**2)
        target = mission.update(0, 0, 0, 0.)
        mission.update(8.2, 0., 0., 1.)  # Old fixed-offset target.
        self.assertNotEqual(mission.stage, 'complete')
        stop_x = target[0]-.34
        mission.update(stop_x, target[1], .5, 2.)
        self.assertEqual(mission.stage, 'complete')
        rear = 1.1*abs(math.cos(.5))+.6*abs(math.sin(.5))
        self.assertGreater(stop_x-rear, 7.)

    def test_terminal_gate_clears_farthest_endpoint_not_mean_plane(self):
        mission = Mission()
        mission.origin, mission.forward, mission.left = (0., 0.), (1., 0.), (0., 1.)
        mapped(mission, [('red', 36.5, -2), ('green', 37.5, 2)], 0.)
        mission.stage, mission.active_ids = 'gate_b', ['buoy-0', 'buoy-1']
        mission.target = (39.2, 0.)
        mission.refresh_target()
        self.assertGreater(mission.gate_finish_s, 37.5+math.hypot(1.1, .6))
        mission.update(38.9, 0., 0., 1.)
        self.assertNotEqual(mission.stage, 'complete')
        target = mission.target
        mission.update(target[0]-.34, target[1], 0., 2.)
        self.assertEqual(mission.stage, 'complete')

    def test_exit_uncertainty_projects_covariance_onto_course_direction(self):
        goals = []
        for angle in (0., math.pi/2):
            mission = Mission(turns=0)
            mission.origin = (0., 0.)
            mission.forward = (math.cos(angle), math.sin(angle))
            mission.left = (-math.sin(angle), math.cos(angle))
            mission.stage = 'gate_a'
            buoy = Landmark('one', 'red', 0., 0., 0., 5, (.04, 0., 0., 1.))
            goals.append(mission.gate_exit_goal([buoy], 0.))
        self.assertAlmostEqual(goals[1]-goals[0], 2*(1.-.2))

    def test_nonterminal_entry_does_not_extend_through_next_course_turn(self):
        mission = Mission()
        mapped(mission, [('red', 7, -2), ('green', 7, 2), ('red', 13, 0)], 0.)
        for buoy in mission.landmarks:
            buoy.covariance = (4., 0., 0., 4.)
        self.assertEqual(mission.update(0, 0, 0, 0.), (9.2, 0.))
        self.assertIsNone(mission.gate_finish_s)


if __name__ == '__main__':
    unittest.main()

"""Safety properties of planning on an incomplete RGB-derived map."""
import math
from concurrent.futures import Future
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ros_ws/src/maritime_navigation'))
from maritime_navigation.costmap import InputProgress, PlanningGridCache, SnapshotPair, active_bearings, planning_grid, resample_physical, swept_clear
from maritime_navigation.mission import observation_goals


def track(x=5., y=0., variance=.04, lifecycle='confirmed'):
    return SimpleNamespace(x=x, y=y, covariance=[variance, 0., 0., variance],
                           footprint_radius_m=.35, lifecycle=lifecycle)


class ControlledExecutor:
    """Complete builds explicitly to exercise a slow worker without sleeping."""
    def __init__(self):
        self.jobs = []

    def submit(self, build):
        future = Future()
        self.jobs.append((future, build))
        return future

    def finish(self):
        future, build = self.jobs.pop(0)
        try:
            future.set_result(build())
        except Exception as error:
            future.set_exception(error)


class CostmapTests(unittest.TestCase):
    def test_sparse_bearing_costs_match_direct_angular_policy(self):
        origin, resolution, bounds = (-10., -10.), .25, [-8, -8, 18, 8]
        source = np.zeros((80, 120), dtype=np.int8)
        yy, xx = np.indices(source.shape)
        xx, yy = origin[0]+(xx+.5)*resolution, origin[1]+(yy+.5)*resolution
        for mode in ('graded', 'hard'):
            for heading, variance in [(-3.13, .001), (3.13, .001), (.7, .1), (-2., .5), (1., 3.)]:
                bearing = SimpleNamespace(origin_x=.125, origin_y=.125,
                    world_bearing_rad=heading, bearing_variance=variance)
                expected = planning_grid(source, origin, resolution, bounds, [])
                distance = np.hypot(xx-bearing.origin_x, yy-bearing.origin_y)
                angle = np.arctan2(yy-bearing.origin_y, xx-bearing.origin_x)-heading
                angle = np.arctan2(np.sin(angle), np.cos(angle))
                width = max(math.radians(3), 3*math.sqrt(variance))
                padding = np.arcsin(np.minimum(1., (.35+.15+resolution)/np.maximum(distance, .01)))
                sector = np.abs(angle) <= width+padding
                if mode == 'hard':
                    expected[sector] = 100
                else:
                    soft = np.rint(85*np.clip(1-np.abs(angle)/(width+padding), 0., 1.)).astype(np.int16)
                    expected[sector] = np.maximum(expected[sector], soft[sector])
                actual = planning_grid(source, origin, resolution, bounds, [], bearings=[bearing], uncertainty_mode=mode)
                np.testing.assert_array_equal(actual, expected)

    def test_cached_geometry_does_not_make_republished_evidence_fresh(self):
        executor = ControlledExecutor()
        cache, progress = PlanningGridCache(executor=executor), InputProgress()
        grid = self.grid()
        progress.update('one', 10, 0.)
        self.assertIsNone(cache.update('unchanged-geometry', 0., lambda: grid))
        executor.finish()
        first = cache.update('unchanged-geometry', .01, lambda: grid)
        progress.update('one', 10, 3.)
        self.assertIs(cache.update('unchanged-geometry', 3., lambda: self.fail('Duplicate rebuild')), first)
        self.assertFalse(progress.ready(3.))
        progress.update('one', 11, 3.1)
        self.assertTrue(progress.ready(3.1))
        self.assertEqual(cache.builds, 1)

    def test_new_obstacle_replaces_cached_grid_when_worker_finishes(self):
        executor = ControlledExecutor()
        cache = PlanningGridCache(executor=executor)
        cache.update('clear', 0., self.grid)
        executor.finish()
        clear = cache.update('clear', .01, self.grid)
        self.assertTrue(swept_clear(clear, (-10, -10), .25, 0., 0., 0., .4, 0.))
        obstacle = lambda: self.grid([track(x=2.)])
        self.assertIs(cache.update('new-obstacle', .1, obstacle), clear)
        cache.update('new-obstacle', .2, obstacle)
        executor.finish()
        blocked = cache.update('new-obstacle', .3, obstacle)
        self.assertFalse(swept_clear(blocked, (-10, -10), .25, 0., 0., 0., .4, 0.))
        self.assertEqual(cache.builds, 2)

    def test_rejected_grid_is_not_committed_to_cache(self):
        executor = ControlledExecutor()
        cache = PlanningGridCache(executor=executor)
        cache.update('clear', 0., self.grid)
        executor.finish()
        cache.update('clear', .01, self.grid)
        cache.update('invalid', .2, lambda: self.grid([track(variance=-1.)]))
        executor.finish()
        with self.assertRaises(ValueError):
            cache.update('invalid', .3, self.grid)
        self.assertEqual(cache.key, 'clear')
        self.assertEqual(cache.builds, 1)

    def test_slow_worker_is_bounded_and_cannot_authorize_stale_geometry(self):
        executor = ControlledExecutor()
        cache = PlanningGridCache(executor=executor)
        cache.update('clear', 0., self.grid)
        executor.finish()
        cache.update('clear', .01, self.grid)
        cache.update('obstacle', .2, lambda: self.grid([track(x=2.)]))
        self.assertIsNone(cache.update('newer-obstacle', .51, self.grid))
        self.assertEqual(len(executor.jobs), 1, 'Do not queue obsolete geometry')
        executor.finish()
        self.assertIsNone(cache.update('newer-obstacle', .8, self.grid))
        self.assertEqual(len(executor.jobs), 1)

    def test_opposing_survey_viewpoints_fit_declared_start_with_turning_hull(self):
        start = (0., 0., .7)
        grid = planning_grid(np.full((200, 300), -1), (-10., -10.), .1, [-8, -8, 18, 8], [],
                             assumed_water=True, clear_start=start, restrict_to_start=True)
        goals = observation_goals(*start)
        self.assertGreater(math.dist(goals[0][:2], goals[1][:2]), 3.)
        for goal in goals:
            self.assertTrue(swept_clear(grid, (-10., -10.), .1, *goal, 0., .35))

    def test_bearing_hazards_follow_mapper_lifecycle_without_topic_races(self):
        records = {identity: (stamp, SimpleNamespace(world_id=identity)) for identity, stamp in
                   [('retired', 10), ('active', 10), ('positioned', 10), ('ahead-of-map', 12), ('', 10)]}
        active = active_bearings(records, [SimpleNamespace(world_id='positioned')], ['active'], 11)
        self.assertEqual(set(active), {'active', 'ahead-of-map', ''})
        active = active_bearings(active, [], ['active'], 12)
        self.assertEqual(set(active), {'active', ''})

    def test_separate_topic_arrivals_keep_last_complete_snapshot(self):
        pairs = SnapshotPair()
        self.assertIsNone(pairs.push('map', 1, 'map-one'))
        self.assertEqual(pairs.push('grid', 1, 'grid-one'), ('map-one', 'grid-one'))
        self.assertEqual(pairs.push('map', 2, 'map-two'), ('map-one', 'grid-one'))
        self.assertEqual(pairs.push('grid', 2, 'grid-two'), ('map-two', 'grid-two'))
        for stamp in range(3, 50):
            pairs.push('map', stamp, 'pending')
        self.assertLessEqual(len(pairs.maps), 10)

    def grid(self, tracks=(), assumed=True, source=None):
        if source is None:
            source = np.full((80, 120), -1)
        return planning_grid(source, (-10., -10.), .25, [-8, -8, 18, 8], tracks,
                             assumed_water=assumed)

    def test_unknown_water_requires_explicit_policy_and_bounds(self):
        unknown = self.grid(assumed=False)
        allowed = self.grid()
        self.assertEqual(unknown[40, 40], -1)
        self.assertEqual(allowed[40, 40], 0)
        self.assertEqual(allowed[0, 0], 100)
        self.assertEqual(allowed[40, 119], 100)

    def test_physical_obstacles_survive_and_input_is_not_mutated(self):
        source = np.full((80, 120), -1)
        source[40, 50] = 100
        result = self.grid(source=source)
        self.assertEqual(result[40, 50], 100)
        self.assertEqual(source[40, 40], -1)

    def test_uncertainty_expands_and_refinement_removes_old_footprints(self):
        small = self.grid([track()])
        uncertain = self.grid([track(variance=1.)])
        self.assertGreater(np.sum(uncertain > 0), np.sum(small > 0))
        self.assertEqual(np.sum(uncertain == 100), np.sum(small == 100))
        moved = self.grid([track(x=10)])
        self.assertEqual(moved[40, 60], 0)
        self.assertEqual(moved[40, 80], 100)

    def test_tentative_and_lost_tracks_remain_collision_obstacles(self):
        for state in ['tentative', 'confirmed', 'stale', 'inconsistent']:
            self.assertEqual(self.grid([track(lifecycle=state)])[40, 60], 100)

    def test_invalid_uncertainty_rejected(self):
        for variance in [-1., math.nan]:
            with self.assertRaises(ValueError):
                self.grid([track(variance=variance)])

    def test_hull_sweep_stops_before_obstacle_and_unknown(self):
        blocked = self.grid([track(x=2.)])
        self.assertFalse(swept_clear(blocked, (-10, -10), .25, 0., 0., 0., .4, 0.))
        self.assertTrue(swept_clear(self.grid(), (-10, -10), .25, 0., 0., 0., .4, 0.))
        self.assertFalse(swept_clear(self.grid(assumed=False), (-10, -10), .25, 0., 0., 0., .4, 0.))

    def test_gate_constraint_prevents_outside_shortcut(self):
        grid = planning_grid(np.zeros((80, 120)), (-10, -10), .25, [-8, -8, 18, 8], [],
                             constraints=[((0, 0), (1, 0), (0, 1), 5., -2., 2.)])
        self.assertEqual(grid[40, 60], 0)
        self.assertEqual(grid[60, 60], 100)

    def test_unresolved_range_is_graded_or_strict_without_clearing_occupancy(self):
        bearing = SimpleNamespace(origin_x=0., origin_y=0., world_bearing_rad=0., bearing_variance=.001)
        source = np.full((80, 120), -1)
        grid = planning_grid(source, (-10, -10), .25, [-8, -8, 18, 8], [],
                             assumed_water=True, bearings=[bearing])
        self.assertGreater(grid[40, 60], 0)
        self.assertLess(grid[40, 60], 100)
        self.assertEqual(grid[60, 60], 0)
        strict = planning_grid(source, (-10, -10), .25, [-8, -8, 18, 8], [],
                               assumed_water=True, bearings=[bearing], uncertainty_mode='hard')
        self.assertEqual(strict[40, 60], 100)
        source[40, 60] = 100
        physical = planning_grid(source, (-10, -10), .25, [-8, -8, 18, 8], [],
                                 assumed_water=True, bearings=[bearing])
        unknown = planning_grid(source, (-10, -10), .25, [-8, -8, 18, 8], [], bearings=[bearing])
        self.assertEqual(physical[40, 60], 100)
        self.assertEqual(unknown[40, 60], 100)
        self.assertEqual(unknown[40, 59], -1)
        startup = planning_grid(source, (-10, -10), .25, [-8, -8, 18, 8], [],
                                assumed_water=True, bearings=[bearing], clear_start=(0., 0., 0.))
        self.assertEqual(startup[40, 48], 0)
        self.assertGreater(startup[40, 64], 0)
        self.assertLess(startup[40, 64], 100)

    def test_clear_start_never_erases_metric_obstacle(self):
        grid = planning_grid(np.full((80, 120), -1), (-10, -10), .25, [-8, -8, 18, 8],
                             [track(x=2.)], assumed_water=True, clear_start=(0., 0., 0.))
        self.assertEqual(grid[40, 48], 100)

    def test_graded_uncertainty_allows_narrow_gate_with_physical_clearance(self):
        source, origin = resample_physical(np.full((80, 120), -1), (-10, -10), .25, [-8, -8, 18, 8])
        obstacles = [track(x=5., y=-1.5, variance=.25**2), track(x=5., y=1.5, variance=.25**2)]
        graded = planning_grid(source, origin, .1, [-8, -8, 18, 8], obstacles, assumed_water=True)
        hard = planning_grid(source, origin, .1, [-8, -8, 18, 8], obstacles,
                             assumed_water=True, uncertainty_mode='hard')
        self.assertTrue(swept_clear(graded, origin, .1, 5., 0., 0., .1, 0.))
        self.assertFalse(swept_clear(hard, origin, .1, 5., 0., 0., .1, 0.))
        self.assertTrue(np.any((graded > 0) & (graded < 100)))

    def test_resampling_retains_coarse_physical_obstacle_and_unknown(self):
        source = np.full((20, 20), -1)
        source[10, 10] = 100
        fine, origin = resample_physical(source, (-5, -5), .5, [-4, -4, 4, 4])
        self.assertEqual(fine[int((.25-origin[1])/.1), int((.25-origin[0])/.1)], 100)
        self.assertEqual(fine[int((-1-origin[1])/.1), int((-1-origin[0])/.1)], -1)

    def test_republication_is_not_new_sensor_evidence(self):
        progress = InputProgress()
        progress.update('one', 10, 0.)
        progress.update('one', 10, 3.)
        self.assertFalse(progress.ready(3.))
        progress.update('one', 11, 3.1)
        self.assertTrue(progress.ready(3.2))

    def test_session_reset_and_time_reversal_latch(self):
        for session, stamp in [('two', 11), ('one', 9)]:
            progress = InputProgress()
            progress.update('one', 10, 0.)
            progress.update(session, stamp, .1)
            self.assertFalse(progress.ready(.2))
            self.assertIsNotNone(progress.fault)


if __name__ == '__main__':
    unittest.main()

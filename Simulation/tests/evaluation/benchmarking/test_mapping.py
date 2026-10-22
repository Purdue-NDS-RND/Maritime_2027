"""RGB map behavior under known geometry, repeated classes, bad timing and outliers."""

from dataclasses import replace
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from maritime_localization.bearing import Bearing, initialize, wrap
from maritime_localization.mapping import BearingMapper, MappingSettings
from maritime_localization.timing import PoseBuffer, TimedPose


def view(stamp, origin, target=(10., 3.), category='red', camera='camera_0', noise=0.):
    delta = np.asarray(target)-origin
    return Bearing(stamp, camera, np.asarray(origin, dtype=float),
                   float(np.arctan2(delta[1], delta[0])+noise), np.deg2rad(1.)**2,
                   np.eye(2)*.15**2, category, f'{camera}:{stamp}:{category}')


def mapped(settings=None):
    mapper = BearingMapper(settings)
    for index in range(35):
        stamp = 1_000_000_000+index*250_000_000
        mapper.process(stamp, [view(stamp, (0., index*.25))])
    return mapper


class MappingTests(unittest.TestCase):
    def test_informative_motion_initializes_and_confirms_stationary_buoy(self):
        mapper = mapped()
        track, = mapper.snapshot()
        np.testing.assert_allclose(track.mean, (10., 3.), atol=.02)
        self.assertEqual(track.state, 'confirmed')
        self.assertGreater(track.confirmation_evidence, 2)
        self.assertTrue(np.linalg.eigvalsh(track.covariance).min() >= .25**2-1e-8)
        self.assertLessEqual(len(track.provenance), 40)

    def test_single_ray_rotation_and_direct_approach_remain_unresolved(self):
        for mode in ('rotation', 'direct'):
            mapper = BearingMapper()
            for index in range(30):
                stamp = 1_000_000_000+index*250_000_000
                origin = (0., 0.) if mode == 'rotation' else (index*.1, 0.)
                mapper.process(stamp, [view(stamp, origin, (10., 0.))])
            self.assertEqual(mapper.snapshot(), [])
            self.assertEqual(len(mapper.tracks), 1)

    def test_robust_initializer_rejects_outlier_without_poisoning_metric_fit(self):
        views = [view(1+i, (0., i*.4)) for i in range(20)]
        views[5].angle += .5
        views[11].angle -= .4
        fit = initialize(views, MappingSettings())
        self.assertIsNotNone(fit)
        np.testing.assert_allclose(fit[0], (10., 3.), atol=.1)
        self.assertEqual(fit[2], 18)

    def test_poor_range_geometry_and_false_positive_cannot_initialize(self):
        views = [view(i, (0., i*.001), (1000., 10.)) for i in range(10)]
        self.assertIsNone(initialize(views, MappingSettings()))
        mapper = BearingMapper()
        mapper.process(1, [view(1, (0., 0.))])
        mapper.process(10_000_000_000, [])
        self.assertEqual(mapper.tracks, [])

    def test_two_red_buoys_keep_distinct_world_ids_when_detection_order_changes(self):
        mapper = BearingMapper()
        targets = [(10., 3.), (10., 8.)]
        for i in range(25):
            stamp = 1_000_000_000+i*250_000_000
            measurements = [view(stamp, (0., i*.25), target) for target in targets]
            mapper.process(stamp, measurements if i%2 else measurements[::-1])
        tracks = mapper.snapshot()
        self.assertEqual(len(tracks), 2)
        self.assertEqual(len({track.identifier for track in tracks}), 2)
        for target in targets:
            self.assertLess(min(np.linalg.norm(track.mean-target) for track in tracks), .1)

    def test_ambiguous_assignment_defers_without_adding_duplicate(self):
        mapper = mapped()
        track = mapper.snapshot()[0]
        before = track.mean.copy()
        stamp = mapper.last_stamp_ns+250_000_000
        measurements = [view(stamp, (0., 8.75)), view(stamp, (0., 8.75))]
        mapper.process(stamp, measurements)
        np.testing.assert_equal(track.mean, before)
        self.assertEqual(len(mapper.tracks), 1)
        self.assertEqual(mapper.diagnostics['ambiguous_observation'], 2)

    def test_overlap_camera_updates_same_authoritative_id(self):
        mapper = mapped()
        track = mapper.snapshot()[0]
        identifier = track.identifier
        stamp = mapper.last_stamp_ns+500_000_000
        mapper.process(stamp, [view(stamp, (.4, 9.), camera='camera_1')])
        self.assertEqual(len(mapper.tracks), 1)
        self.assertEqual(track.identifier, identifier)
        self.assertEqual(track.cameras, {'camera_0', 'camera_1'})

    def test_confirmed_identity_survives_occlusion_and_stale_reacquisition(self):
        mapper = mapped()
        track = mapper.snapshot()[0]
        stamp = mapper.last_stamp_ns+10_000_000_000
        mapper.process(stamp, [])
        self.assertEqual(track.state, 'stale')
        mapper.process(stamp+250_000_000, [view(stamp+250_000_000, (0., 9.))])
        self.assertEqual(track.state, 'confirmed')
        self.assertEqual(len(mapper.tracks), 1)

    def test_initialization_evidence_is_consumed_without_double_filter_update(self):
        mapper = BearingMapper()
        for i in range(30):
            stamp = 1_000_000_000+i*250_000_000
            mapper.process(stamp, [view(stamp, (0., i*.25))])
            if mapper.snapshot():
                track = mapper.snapshot()[0]
                self.assertEqual(track.state, 'tentative')
                self.assertEqual(track.confirmation_evidence, 0)
                self.assertEqual(mapper.diagnostics['ekf_update'], 0)
                break
        else:
            self.fail('No initialization')

    def test_repeated_redundant_frames_do_not_collapse_covariance(self):
        mapper = mapped()
        track = mapper.snapshot()[0]
        before = track.confirmation_evidence
        for i in range(10):
            stamp = mapper.last_stamp_ns+10_000_000
            mapper.process(stamp, [view(stamp, (0., 8.5))])
        self.assertEqual(track.confirmation_evidence, before)

    def test_late_updates_and_paused_sessions_do_not_mutate_map(self):
        mapper = mapped()
        track = mapper.snapshot()[0]
        before = track.mean.copy()
        mapper.process(1, [view(1, (1., 1.))])
        self.assertEqual(mapper.diagnostics['late_frame_rejected'], 1)
        mapper.pause('origin reset')
        mapper.process(mapper.last_stamp_ns+1, [])
        np.testing.assert_equal(track.mean, before)

    def test_bounded_track_and_keyframe_memory(self):
        mapper = BearingMapper(replace(MappingSettings(), max_tracks=2, max_views=5))
        stamp = 1_000_000_000
        mapper.process(stamp, [view(stamp, (0., 0.), category=str(i)) for i in range(8)])
        self.assertEqual(len(mapper.tracks), 2)
        self.assertEqual(mapper.diagnostics['track_capacity_rejected'], 6)
        for i in range(20):
            stamp += 250_000_000
            mapper.process(stamp, [view(stamp, (i*.25, 0.), (20., 0.), category='0')])
        self.assertLessEqual(len(mapper.tracks[0].views), 5)
        self.assertEqual(mapper.tracks[0].views[0].stamp_ns, 1_000_000_000)

    def test_shared_heading_failure_defers_entire_frame(self):
        mapper = BearingMapper()
        targets = [(10., 3.), (10., 8.), (10., -2.)]
        for i in range(25):
            stamp = 1_000_000_000+i*250_000_000
            mapper.process(stamp, [view(stamp, (0., i*.25), target, category=str(j))
                                   for j, target in enumerate(targets)])
        before = [track.mean.copy() for track in mapper.snapshot()]
        stamp += 250_000_000
        mapper.process(stamp, [view(stamp, (0., 6.25), target, category=str(j), noise=.1)
                               for j, target in enumerate(targets)])
        self.assertEqual(mapper.diagnostics['shared_residual_frame_rejected'], 1)
        for track, previous in zip(mapper.snapshot(), before):
            np.testing.assert_equal(track.mean, previous)

    def test_two_initially_unresolved_overlapping_cameras_do_not_promote_duplicates(self):
        mapper = BearingMapper()
        for i in range(40):
            stamp = 1_000_000_000+i*250_000_000
            for camera, x in (('camera_0', 0.), ('camera_1', .4)):
                mapper.process(stamp, [view(stamp, (x, i*.25), camera=camera)])
        self.assertEqual(len(mapper.snapshot()), 1)
        track = mapper.snapshot()[0]
        self.assertEqual(track.state, 'confirmed')
        self.assertEqual(track.cameras, {'camera_0', 'camera_1'})

    def test_sustained_innovation_failure_marks_inconsistent_without_duplicate(self):
        mapper = mapped()
        track = mapper.snapshot()[0]
        # A very certain track: force a residual outside its uncertainty gate
        # but still within the gross bearing neighborhood of the existing buoy.
        track.covariance = np.eye(2)*.001
        track.last_view = view(mapper.last_stamp_ns, (0., 8.5))
        for i in range(6):
            stamp = mapper.last_stamp_ns+250_000_000
            bad = view(stamp, (0., 8.5), noise=np.deg2rad(7.))
            bad.variance = 1e-7
            bad.pose_covariance = np.eye(2)*1e-7
            mapper.process(stamp, [bad])
        self.assertEqual(track.state, 'inconsistent')
        self.assertEqual(len(mapper.snapshot()), 1)
        self.assertEqual(len(mapper.tracks), 1)

    def test_initializer_covariance_covers_synthetic_random_noise(self):
        rng = np.random.default_rng(7)
        covered = accepted = 0
        for trial in range(30):
            views = [view(i, (0., i*.4), noise=rng.normal(0, np.deg2rad(.8))) for i in range(20)]
            fit = initialize(views, MappingSettings())
            if fit is None:  # Gross-residual quality gate may withhold a noisy initialization.
                continue
            accepted += 1
            error = fit[0]-[10., 3.]
            covered += error @ np.linalg.solve(fit[1], error) < 5.991
        self.assertGreaterEqual(accepted, 25)
        self.assertGreaterEqual(covered, int(.9*accepted))  # Synthetic evidence, not on-water calibration.


class TimingTests(unittest.TestCase):
    def sample(self, stamp, x=0., yaw=0.):
        transform = np.eye(4)
        transform[0, 3] = x
        transform[:3, :3] = Rotation.from_euler('z', yaw).as_matrix()
        return TimedPose(stamp, transform, np.eye(6)*.1)

    def test_interpolates_translation_and_slerp_across_wrapped_heading(self):
        buffer = PoseBuffer(max_gap_s=1.)
        buffer.add(self.sample(1_000_000_000, 1., np.deg2rad(179)))
        buffer.add(self.sample(2_000_000_000, 2., np.deg2rad(-179)))
        pose, bracket = buffer.lookup(1_500_000_000)
        self.assertEqual(bracket, (1_000_000_000, 2_000_000_000))
        self.assertAlmostEqual(pose.transform[0, 3], 1.5)
        self.assertAlmostEqual(abs(Rotation.from_matrix(pose.transform[:3, :3]).as_euler('xyz')[2]), np.pi)
        np.testing.assert_allclose(pose.covariance, np.eye(6)*.1)

    def test_clock_mismatch_stale_missing_bracket_and_gap_rejected(self):
        buffer = PoseBuffer()
        buffer.add(self.sample(1_790_000_000_000_000_000))
        with self.assertRaisesRegex(LookupError, 'clock alignment'):
            buffer.lookup(3_000_000_000)
        buffer = PoseBuffer(max_gap_s=.2)
        buffer.add(self.sample(1_000_000_000))
        buffer.add(self.sample(2_000_000_000))
        with self.assertRaisesRegex(ValueError, 'gap'):
            buffer.lookup(1_500_000_000)

    def test_clock_and_origin_resets_latch_session_fault(self):
        for stamp, x in ((500_000_000, 0.), (1_100_000_000, 100.)):
            buffer = PoseBuffer()
            buffer.add(self.sample(1_000_000_000))
            buffer.add(self.sample(stamp, x))
            self.assertIsNotNone(buffer.fault)
            with self.assertRaises(ValueError):
                buffer.lookup(stamp)

    def test_pose_memory_is_bounded(self):
        buffer = PoseBuffer(max_samples=4)
        for i in range(200):
            buffer.add(self.sample((i+1)*100_000_000))
        self.assertEqual(len(buffer.samples), 4)
        self.assertEqual(len(buffer.trace), 100)

    def test_recorded_submillisecond_turn_is_withheld_until_valid_bracket(self):
        buffer = PoseBuffer()
        buffer.add(self.sample(1_000_000_000))
        buffer.add(self.sample(1_000_446_000, yaw=.001834))
        self.assertIsNone(buffer.fault)
        self.assertEqual(buffer.withheld, 1)
        self.assertEqual(len(buffer.samples), 1)
        with self.assertRaises(LookupError):
            buffer.lookup(1_000_446_000)
        buffer.add(self.sample(1_020_000_000, yaw=.002))
        _, bracket = buffer.lookup(1_000_446_000)
        self.assertEqual(bracket, (1_000_000_000, 1_020_000_000))

    def test_microinterval_large_jumps_still_latch_immediately(self):
        for x, yaw in [(1., 0.), (0., .2)]:
            buffer = PoseBuffer()
            buffer.add(self.sample(1_000_000_000))
            buffer.add(self.sample(1_000_446_000, x=x, yaw=yaw))
            self.assertIsNotNone(buffer.fault)
            buffer.add(self.sample(1_100_000_000))
            with self.assertRaises(ValueError):
                buffer.lookup(1_000_000_000)

    def test_withheld_poses_cannot_hide_clock_reversal_or_duplicate_conflict(self):
        for stamp, yaw in [(1_000_400_000, .001), (1_000_446_000, .002)]:
            buffer = PoseBuffer()
            buffer.add(self.sample(1_000_000_000))
            buffer.add(self.sample(1_000_446_000, yaw=.001834))
            buffer.add(self.sample(stamp, yaw=yaw))
            self.assertIn('clock rewound or conflicting duplicate', buffer.fault)

    def test_fast_continuous_motion_is_checked_against_accepted_anchor(self):
        buffer = PoseBuffer()
        buffer.add(self.sample(1_000_000_000))
        # Each 1 ms increment looks small, but sustained 5 rad/s exceeds 4.
        for i in range(1, 22):
            buffer.add(self.sample(1_000_000_000+i*1_000_000, yaw=i*.005))
        self.assertIsNotNone(buffer.fault)
        self.assertEqual(len(buffer.samples), 1)

    def test_subwindow_noise_does_not_refresh_history_or_bypass_gap_limit(self):
        buffer = PoseBuffer()
        buffer.add(self.sample(1_000_000_000))
        for i in range(1, 20):
            buffer.add(self.sample(1_000_000_000+i*1_000_000, yaw=.001*(-1)**i))
        self.assertEqual(len(buffer.samples), 1)
        buffer.add(self.sample(1_400_000_000))
        with self.assertRaisesRegex(ValueError, 'gap'):
            buffer.lookup(1_010_000_000)
        self.assertLessEqual(len(buffer.trace), 100)


if __name__ == '__main__':
    unittest.main()

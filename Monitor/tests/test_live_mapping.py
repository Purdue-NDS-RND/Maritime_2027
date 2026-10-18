"""Run with make -C autonomy mapping-test; ROS traffic stays in a test container."""
import copy
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/opt/live')
import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import TransformStamped
from maritime_interfaces.msg import BuoyMap
from nav_msgs.msg import OccupancyGrid, Odometry
import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image, TimeReference
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster
from visualization_msgs.msg import Marker, MarkerArray

from live_clock import ALIGNED_POSE, LiveClock
from live_geometry import DisplayAlignment, ReceiptClock, ellipse, ns, rotation
from mapping_view import MappingView, Plot


class GeometryTests(unittest.TestCase):
    def test_epoch_clock_interpolation_no_extrapolation_and_bounded_history(self):
        bridge = ReceiptClock()
        epoch = 1_790_000_000_000_000_000
        for index in range(60):
            bridge.add(epoch+index*1_400_000_000, 10_000_000_000+index*1_000_000_000)
        self.assertEqual(len(bridge.knots), 40)
        self.assertEqual(bridge.convert(epoch+58*1_400_000_000+700_000_000), 68_500_000_000)
        with self.assertRaises(LookupError):
            bridge.convert(epoch)
        with self.assertRaises(LookupError):
            bridge.convert(epoch+60*1_400_000_000)

    def test_reset_gap_and_pause(self):
        bridge = ReceiptClock()
        bridge.add(1_000_000_000, 1_000_000_000)
        bridge.add(1_200_000_000, 1_000_000_000)
        self.assertEqual(len(bridge.knots), 1)
        with self.assertRaises(ValueError):
            bridge.add(900_000_000, 1_100_000_000)
        with self.assertRaises(ValueError):
            bridge.convert(1_000_000_000)
        gap = ReceiptClock()
        gap.add(1, 1)
        with self.assertRaises(ValueError):
            gap.add(3_000_000_001, 1_000_000_001)

    def test_rotated_truth_frame_and_covariance_ellipse(self):
        alignment = DisplayAlignment()
        alignment.set([10, 20], math.pi/2, [2, 3], math.pi)
        np.testing.assert_allclose(alignment.point([11, 20]), [2, 4], atol=1e-8)
        curve = ellipse([2, 3], [4, 0, 0, 1])
        np.testing.assert_allclose(curve.max(axis=1), [8, 6])
        np.testing.assert_allclose(curve.min(axis=1), [-4, 0])

    def test_live_receipt_jitter_waits_for_valid_bracket_without_extrapolation(self):
        bridge = ReceiptClock()
        self.assertTrue(bridge.add(1_000_000_000, 1_000_000_000, defer_arrival_jitter=True))
        self.assertFalse(bridge.add(1_020_000_000, 1_120_000_000, defer_arrival_jitter=True))
        self.assertEqual(bridge.deferred, 1)
        self.assertIsNone(bridge.fault)
        with self.assertRaises(LookupError):
            bridge.convert(1_010_000_000)
        self.assertTrue(bridge.add(1_200_000_000, 1_220_000_000, defer_arrival_jitter=True))
        self.assertEqual(bridge.convert(1_100_000_000), 1_110_000_000)

    def test_live_jitter_mode_still_latches_resets_and_persistent_gaps(self):
        for source, target in [(900_000_000, 1_100_000_000),
                               (1_100_000_000, 900_000_000),
                               (3_100_000_000, 1_021_000_000)]:
            bridge = ReceiptClock()
            bridge.add(1_000_000_000, 1_000_000_000, defer_arrival_jitter=True)
            bridge.add(1_100_000_000, 1_001_000_000, defer_arrival_jitter=True)
            with self.subTest(source=source, target=target), self.assertRaises(ValueError):
                bridge.add(source, target, defer_arrival_jitter=True)
            with self.assertRaises(ValueError):
                bridge.convert(1_000_000_000)

    def test_strict_clock_keeps_original_slope_fault(self):
        bridge = ReceiptClock()
        bridge.add(1_000_000_000, 1_000_000_000)
        with self.assertRaisesRegex(ValueError, 'Implausible'):
            bridge.add(1_020_000_000, 1_120_000_000)


def stamp(message_stamp, value):
    message_stamp.sec, message_stamp.nanosec = divmod(value, 1_000_000_000)


class PlotTests(unittest.TestCase):
    def setUp(self):
        import matplotlib
        matplotlib.use('Agg')
        self.track = SimpleNamespace(world_id='buoy-1', category='red', lifecycle='confirmed',
                                     x=4., y=3., covariance=[.2, 0., 0., .1])
        self.node = SimpleNamespace(path=[np.array([0., 0.]), np.array([1., 0.])],
            boat=(np.array([1., 0.]), 0.), alignment=DisplayAlignment(), truth={},
            truth_arrivals={}, mapping=SimpleNamespace(tracks=[self.track], paused=False),
            history={'buoy-1': [(0., 4., 3., .2, .1), (1., 4.1, 3., .1, .1)]},
            diagnostic='Ready', map_arrival=time.monotonic(), clock_detail='Source stamps')
        self.plot = Plot(self.node)

    def tearDown(self):
        self.plot.plt.close(self.plot.figure)

    def test_updates_reuse_artists_and_preserve_toolbar_zoom(self):
        plot = self.plot
        plot.draw()
        artists = tuple(plot.map.lines)
        legend = plot.map.get_legend()
        for axis in (plot.map, plot.mean, plot.variance):
            axis.set_xlim(1., 2.)
            axis.set_ylim(2., 3.)
        self.track.x = 6.
        self.node.history['buoy-1'].append((2., 6., 3., .1, .1))
        plot.draw()
        self.assertEqual(tuple(plot.map.lines), artists)
        self.assertIs(plot.map.get_legend(), legend)
        self.assertEqual(plot.tracks['buoy-1'][1].get_xdata()[0], 6.)
        for axis in (plot.map, plot.mean, plot.variance):
            self.assertEqual(axis.get_xlim(), (1., 2.))
            self.assertEqual(axis.get_ylim(), (2., 3.))
        plot.key(SimpleNamespace(key='a'))
        plot.key(SimpleNamespace(key='a'))
        plot.draw()
        self.assertGreater(plot.map.get_xlim()[1], 6.)

    def test_track_removal_and_truth_reset_remove_obsolete_artists(self):
        self.node.alignment.set([0., 0.], 0., [0., 0.], 0.)
        self.node.alignment_residual = 0.
        self.node.truth['red_buoy'] = np.array([4., 3.])
        self.node.truth_arrivals['red_buoy'] = time.monotonic()
        self.plot.draw()
        self.assertTrue(self.plot.truth)
        self.node.mapping.tracks = []
        self.node.alignment = DisplayAlignment()
        self.plot.draw()
        self.assertFalse(self.plot.tracks)
        self.assertFalse(self.plot.truth)
        self.assertEqual(len(self.plot.map.lines), 3)  # Boat, path, heading remain.
        self.assertEqual(len(self.plot.mean.lines), 0)
        self.assertIsNone(self.plot.mean.get_legend())
        self.assertNotIn('buoy-1', [t.get_text() for t in self.plot.map.get_legend().get_texts()])

    def test_lifecycle_and_stale_status_remain_visible(self):
        self.plot.draw()
        self.track.lifecycle = 'stale'
        self.node.map_arrival -= 3.
        self.plot.draw()
        self.assertEqual(self.plot.tracks['buoy-1'][0].get_linestyle(), '--')
        self.assertIn('stale', self.plot.map.get_legend().get_texts()[-1].get_text())
        self.assertIn('MAP INPUT STALE', self.plot.title.get_text())
        self.node.mapping.paused = True
        self.node.mapping.detail = 'Pose reset'
        self.plot.draw()
        self.assertIn('MAPPING PAUSED: Pose reset', self.plot.title.get_text())

    def test_map_scale_and_panel_stay_stable_until_content_reaches_edge(self):
        self.plot.draw()
        limits = self.plot.map.get_xlim(), self.plot.map.get_ylim()
        self.assertEqual(limits, ((-10., 10.), (-10., 10.)))
        panel = self.plot.map.get_position().bounds
        for x in (2., 5., 7.):
            self.node.boat = (np.array([x, 0.]), 0.)
            self.plot.draw()
            self.assertEqual((self.plot.map.get_xlim(), self.plot.map.get_ylim()), limits)
            np.testing.assert_allclose(self.plot.map.get_position().bounds, panel)
        self.node.mapping.tracks.append(SimpleNamespace(world_id='buoy-2', category='green',
            lifecycle='tentative', x=-3., y=-2., covariance=[.1, 0., 0., .1]))
        self.node.history['buoy-2'] = []
        self.plot.draw()
        self.assertEqual((self.plot.map.get_xlim(), self.plot.map.get_ylim()), limits)
        self.node.boat = (np.array([25., 0.]), 0.)
        self.plot.draw()
        expanded = self.plot.map.get_xlim(), self.plot.map.get_ylim()
        self.assertGreater(expanded[0][1], 26.)
        np.testing.assert_allclose(self.plot.map.get_position().bounds, panel)
        self.node.boat = (np.array([0., 0.]), 0.)
        self.plot.draw()
        self.assertEqual((self.plot.map.get_xlim(), self.plot.map.get_ylim()), expanded)


class LivePipelineTests(unittest.TestCase):
    def test_tk_popup_on_virtual_display(self):
        script = '''
import sys
sys.path.insert(0, '/opt/live')
import matplotlib
matplotlib.use('TkAgg')
import rclpy
from mapping_view import MappingView, Plot
rclpy.init()
node = MappingView('/unused/pose')
plot = Plot(node)
plot.draw()
plot.plt.pause(.3)
assert plot.plt.fignum_exists(plot.figure.number)
plot.plt.close(plot.figure)
node.destroy_node()
rclpy.shutdown()
'''
        subprocess.run(['xvfb-run', '-a', 'python3', '-c', script], check=True, timeout=15)

    def test_rgb_live_pipeline_with_clock_bridge_viewer_and_truth_isolation(self):
        import matplotlib
        matplotlib.use('Agg')
        rclpy.init()
        source = Node('live_mapping_fixture')
        clock = LiveClock()
        view = MappingView(ALIGNED_POSE)
        executor = SingleThreadedExecutor()
        for node in (source, clock, view):
            executor.add_node(node)
        qos = qos_profile_sensor_data
        publishers = {
            'image': source.create_publisher(Image, '/sensors/camera_0/color/image_raw', qos),
            'info': source.create_publisher(CameraInfo, '/sensors/camera_0/color/camera_info', qos),
            'pose': source.create_publisher(Odometry, '/mavros/local_position/odom', qos),
            'reference': source.create_publisher(TimeReference, '/mavros/time_reference', qos),
            'clock': source.create_publisher(Clock, '/clock', qos),
            'truth': source.create_publisher(Odometry, '/blueboat/ground_truth/odometry', qos),
            'buoy': source.create_publisher(Odometry, '/blueboat/ground_truth/red_buoy/odometry', qos),
        }
        maps = []
        source.create_subscription(BuoyMap, '/mapping/buoys', maps.append,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        normalized = []
        source.create_subscription(Odometry, ALIGNED_POSE, normalized.append, qos)
        overlays = []
        source.create_subscription(MarkerArray, '/monitor/mapping/markers', overlays.append,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        grids, grid_times, world_grids, world_times = [], [], [], []
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        def receive_grid(message):
            grids.append(message)
            grid_times.append(time.monotonic())
        def receive_world_grid(message):
            world_grids.append(message)
            world_times.append(time.monotonic())
        source.create_subscription(OccupancyGrid, '/mapping/occupancy_grid', receive_grid, durable)
        source.create_subscription(OccupancyGrid, '/monitor/mapping/occupancy_grid', receive_world_grid, durable)
        transform = TransformStamped()
        transform.header.frame_id, transform.child_frame_id = 'base_link', 'camera_optical'
        transform.transform.rotation.x, transform.transform.rotation.y = -.5, .5
        transform.transform.rotation.z, transform.transform.rotation.w = -.5, .5
        broadcaster = StaticTransformBroadcaster(source)
        broadcaster.sendTransform(transform)
        log = open('/tmp/live-pipeline-test.log', 'w+')
        parameters = Path('/tmp/live-test-mapper.yaml')
        parameters.write_text('/localization/buoy_mapper:\n  ros__parameters:\n    pose_wait_s: 2.0\n')
        process = subprocess.Popen(['ros2', 'launch', 'maritime_localization', 'pipeline.launch.py',
            'use_sim_time:=true', f'pose_topic:={ALIGNED_POSE}', f'mapper_parameters:={parameters}'],
            stdout=log, stderr=subprocess.STDOUT)
        popup = subprocess.Popen(['xvfb-run', '-a', 'python3', '/opt/live/mapping_view.py',
            '--plot-only', '--pose-topic', ALIGNED_POSE], stdout=log, stderr=subprocess.STDOUT)

        def spin(seconds):
            end = time.monotonic()+seconds
            while time.monotonic() < end:
                executor.spin_once(timeout_sec=.005)

        try:
            spin(2.)
            info = CameraInfo(width=420, height=180)
            info.header.frame_id = 'camera_optical'
            info.k = [200., 0., 210., 0., 200., 90., 0., 0., 1.]
            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            marker = cv2.aruco.drawMarker(dictionary, 1, 80)
            bridge = CvBridge()
            # Truth is deliberately in a translated/rotated frame. The truth buoy
            # is deliberately FALSE, ensuring it cannot drive the estimated mean.
            r = rotation(.4)
            translation = np.array([20., -8.])
            for index in range(85):
                sim = 10_000_000_000+index*100_000_000
                epoch = 1_790_000_000_000_000_000+round(sim*1.4)
                tick = Clock()
                stamp(tick.clock, sim)
                publishers['clock'].publish(tick)
                spin(.01)
                pose = Odometry()
                pose.header.frame_id, pose.child_frame_id = 'map', 'base_link'
                stamp(pose.header.stamp, epoch)
                pose.pose.pose.position.y = min(index, 59)*.1
                pose.pose.pose.orientation.w = 1.
                pose.twist.twist.linear.y = 1.
                publishers['pose'].publish(pose)
                truth = copy.deepcopy(pose)
                truth.header.frame_id = 'world'
                stamp(truth.header.stamp, sim)
                world_xy = r @ np.array([0., pose.pose.pose.position.y])+translation
                truth.pose.pose.position.x, truth.pose.pose.position.y = map(float, world_xy)
                truth.pose.pose.orientation.z, truth.pose.pose.orientation.w = math.sin(.2), math.cos(.2)
                publishers['truth'].publish(truth)
                false_buoy = copy.deepcopy(truth)
                false_buoy.pose.pose.position.x = 999.
                publishers['buoy'].publish(false_buoy)
                # Exercise slow, one-Hz FCU references and delayed pose conversion.
                if index % 10 == 0:
                    reference = TimeReference(source='fcu')
                    stamp(reference.header.stamp, epoch)
                    stamp(reference.time_ref, 1_789_000_000_000_000_000+sim)
                    publishers['reference'].publish(reference)
                if index < 60:
                    image = np.full((180, 420, 3), 255, dtype=np.uint8)
                    left = 40+index*4
                    image[50:130, left:left+80] = marker[:, :, None]
                    rgb = bridge.cv2_to_imgmsg(image, encoding='bgr8')
                    rgb.header.frame_id = 'camera_optical'
                    stamp(rgb.header.stamp, sim)
                    info.header.stamp = rgb.header.stamp
                    publishers['info'].publish(info)
                    publishers['image'].publish(rgb)
                spin(.09)
            spin(1.)
            self.assertIsNone(clock.fault)
            self.assertGreater(len(normalized), 40)
            self.assertTrue(all(ns(a.header.stamp) < ns(b.header.stamp)
                                for a, b in zip(normalized, normalized[1:])))
            self.assertGreater(normalized[-1].pose.covariance[0], 0.)
            confirmed = [m for m in maps if m.tracks and m.tracks[0].lifecycle == 'confirmed']
            self.assertTrue(confirmed, Path('/tmp/live-pipeline-test.log').read_text())
            track = confirmed[-1].tracks[0]
            self.assertAlmostEqual(track.x, 5., delta=.25)
            self.assertAlmostEqual(track.y, 3.2625, delta=.1)
            self.assertIsNotNone(view.alignment.r)
            np.testing.assert_allclose(view.alignment.point(translation), [0., 0.], atol=.02)
            self.assertGreater(len(view.history[track.world_id]), 3)
            means = [marker for overlay in overlays for marker in overlay.markers
                     if marker.type == Marker.SPHERE and marker.action == Marker.ADD]
            self.assertTrue(means)
            self.assertEqual(means[-1].header.frame_id, 'world')
            expected_world = r @ np.array([track.x, track.y])+translation
            np.testing.assert_allclose([means[-1].pose.position.x, means[-1].pose.position.y],
                                       expected_world, atol=.05)
            # Occupancy is delivered at 10 Hz even after RGB observations stop.
            # Check both the production grid and the display copy, not timer setup.
            for arrivals in (grid_times, world_times):
                recent = [t for t in arrivals if t > arrivals[-1]-2.]
                self.assertGreaterEqual((len(recent)-1)/(recent[-1]-recent[0]), 8.)
            self.assertIsNone(popup.poll(), 'Popup must remain active during grid delivery')
            grid, world_grid = grids[-1], world_grids[-1]
            self.assertEqual((grid.info.width, grid.info.height, grid.info.resolution), (200, 200, .5))
            self.assertIn(100, grid.data)
            self.assertIn(-1, grid.data)
            self.assertNotIn(0, grid.data)  # No fabricated free space.
            self.assertEqual(world_grid.header.frame_id, 'world')
            self.assertEqual(world_grid.data, grid.data)
            origin = world_grid.info.origin
            # Transform a cell centre through the RViz grid origin. It must land
            # in the same translated/rotated world as the truth/marker fixture.
            cell = np.array([100.5, 101.5])*grid.info.resolution
            world_cell = np.array([origin.position.x, origin.position.y])+rotation(.4) @ cell
            expected = r @ (np.array([-50., -50.])+cell)+translation
            np.testing.assert_allclose(world_cell, expected, atol=.02)
            late_grids = []
            source.create_subscription(OccupancyGrid, '/monitor/mapping/occupancy_grid', late_grids.append, durable)
            spin(.3)
            self.assertTrue(late_grids, 'RViz late join must receive the retained grid')
            # Save a representative UI with plausible truth in the display frame;
            # assertions above used false truth to test estimator isolation.
            view.truth['red_buoy'] = r @ np.array([5., 3.2625])+translation
            plot = Plot(view)
            plot.draw()
            snapshot = os.environ.get('LIVE_MAPPING_SNAPSHOT', '/tmp/live-mapping-test.png')
            plot.figure.savefig(snapshot)
            self.assertTrue(Path(snapshot).exists())
            # A reset must latch the adapter and stop normalized pose publication.
            before = clock.converted
            reset = Clock()
            stamp(reset.clock, 1_000_000_000)
            clock.on_clock(reset)
            self.assertIn('rewound', clock.fault)
            clock.on_pose(pose)
            self.assertEqual(clock.converted, before)
        finally:
            import signal
            for child in (process, popup):
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            log.close()
            executor.shutdown()
            for node in (view, clock, source):
                node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()

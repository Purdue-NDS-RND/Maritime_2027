"""Real Nav2 servers + synthetic map/odometry; no vehicle, Gazebo or arming.

Exercises the production supervisor/costmap, Smac State Lattice and RPP in an isolated domain.
The ideal kinematics here are a software integration test, not boat acceptance.
"""
from array import array
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from maritime_interfaces.msg import BearingObservation, BearingObservationArray, BuoyMap, BuoyTrack
from nav_msgs.msg import OccupancyGrid, Odometry, Path as NavigationPath
from std_msgs.msg import String


class Fixture(Node):
    def __init__(self):
        super().__init__('nav2_integration_fixture')
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.maps = self.create_publisher(BuoyMap, '/mapping/buoys', durable)
        self.grids = self.create_publisher(OccupancyGrid, '/mapping/occupancy_grid', durable)
        self.bearings = self.create_publisher(BearingObservationArray, '/mapping/observations', qos_profile_sensor_data)
        self.odom = self.create_publisher(Odometry, '/vessel/odometry', qos_profile_sensor_data)
        self.create_subscription(TwistStamped, '/navigation/velocity', self.on_command, 10)
        self.create_subscription(String, '/navigation/status', self.on_status, 10)
        self.create_subscription(NavigationPath, '/plan', self.on_path, 10)
        self.x = self.y = self.yaw = self.speed = self.rate = 0.
        self.status = {}
        self.last_command = 0.
        self.positions = []
        self.paths = []
        self.commands = []
        self.pending_grids = []
        self.freeze = False
        self.blocked = False
        self.paused = False
        self.session = 'integration-one'
        self.gate = os.environ.get('NAV2_TEST_SCENARIO') == 'gate'
        self.stamp = self.get_clock().now().to_msg()
        self.started = time.monotonic()
        self.create_timer(.1, self.tick)
        self.create_timer(.01, self.release_grid)

    def release_grid(self):
        while self.pending_grids and self.pending_grids[0][0] <= time.monotonic():
            self.grids.publish(self.pending_grids.pop(0)[1])

    def on_command(self, message):
        assert message.header.frame_id == 'base_link'
        self.speed, self.rate = message.twist.linear.x, message.twist.angular.z
        self.last_command = time.monotonic()
        self.commands.append((len(self.positions), self.speed, self.rate))

    def on_path(self, message):
        self.paths.append((len(self.positions), [(p.pose.position.x, p.pose.position.y)
                                               for p in message.poses]))

    def on_status(self, message):
        self.status = json.loads(message.data)

    def tick(self):
        if time.monotonic()-self.last_command > .4:
            self.speed = self.rate = 0.
        self.x += .1*self.speed*math.cos(self.yaw)
        self.y += .1*self.speed*math.sin(self.yaw)
        self.yaw += .1*self.rate
        self.positions.append((self.x, self.y, self.yaw))
        if len(self.positions) % 100 == 0:
            print(f'TRACE: pose=({self.x:.2f}, {self.y:.2f}, {self.yaw:.2f}); '
                  f'command=({self.speed:.2f}, {self.rate:.2f}); '
                  f'status={self.status.get("reason")}', flush=True)
        odom = Odometry()
        odom.header.frame_id, odom.child_frame_id = 'map', 'base_link'
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.pose.pose.position.x, odom.pose.pose.position.y = self.x, self.y
        odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = math.sin(self.yaw/2), math.cos(self.yaw/2)
        odom.twist.twist.linear.x, odom.twist.twist.angular.z = self.speed, self.rate
        self.odom.publish(odom)
        if not self.freeze:
            self.stamp = odom.header.stamp
        mapped = BuoyMap(session_id=self.session, paused=self.paused,
                         detail='Injected permanent pose discontinuity' if self.paused else '')
        mapped.header.frame_id, mapped.header.stamp = 'map', self.stamp
        if time.monotonic()-self.started < 8:
            # An unresolved duplicate can expire while its replacement resolves.
            # It must not leave a permanent navigation-only shadow obstacle.
            mapped.unresolved_world_ids = ['expiring-range-track']
            mapped.unresolved_count = 1
            self.bearings.publish(BearingObservationArray(header=mapped.header, session_id=self.session,
                observations=[BearingObservation(world_id='expiring-range-track', category='green',
                    camera_id='camera_0', world_bearing_rad=.2, bearing_variance=.03)]))
        mapped.tracks = [BuoyTrack(world_id='obstacle', category='blue', lifecycle='confirmed',
            x=5., y=0., covariance=[.01, 0., 0., .01], footprint_radius_m=.35,
            confirmation_evidence=10, observation_count=20, last_seen=self.stamp, last_update=self.stamp)]
        if self.gate:
            mapped.tracks = [BuoyTrack(world_id=color, category=color, lifecycle='confirmed',
                x=7., y=float(y), covariance=[.25**2, 0., 0., .25**2], footprint_radius_m=.35,
                confirmation_evidence=10, observation_count=20, last_seen=self.stamp, last_update=self.stamp)
                for color, y in [('red', -1.5), ('green', 1.5)]]
        grid = OccupancyGrid(header=mapped.header)
        grid.info.width, grid.info.height, grid.info.resolution = 120, 80, .25
        grid.info.origin.position.x, grid.info.origin.position.y = -10., -10.
        grid.info.origin.orientation.w = 1.
        cells = np.full((80, 120), -1, dtype=np.int8)
        if self.gate:
            for buoy in mapped.tracks:
                yy, xx = np.indices(cells.shape)
                dx = np.maximum(np.abs(-10+(xx+.5)*.25-buoy.x)-.125, 0.)
                dy = np.maximum(np.abs(-10+(yy+.5)*.25-buoy.y)-.125, 0.)
                cells[dx*dx+dy*dy <= .35**2] = 100
        else:
            cells[39:42, 59:62] = 100
        if self.blocked:
            cells[:, 59:62] = 100
        grid.data = array('b', cells.ravel())
        self.maps.publish(mapped)
        # Real mapper snapshots arrive on two separate topics. Exercise that
        # delay continuously, rather than only testing simultaneous publication.
        self.pending_grids.append((time.monotonic()+.06, grid))


def until(node, predicate, timeout):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=.05)
        if getattr(node, 'launch_process', None) and node.launch_process.poll() is not None:
            raise AssertionError('Nav2 launch exited unexpectedly')
        if predicate():
            return
    raise AssertionError(f'Timed out: {node.status}; pose={(node.x, node.y, node.yaw)}')


def main():
    log_path = Path('/tmp/nav2-integration.log')
    with log_path.open('w') as log:
        process = subprocess.Popen(['ros2', 'launch', 'maritime_navigation', 'navigation.launch.py',
            'task:='+('gate' if os.environ.get('NAV2_TEST_SCENARIO') == 'gate' else 'goal'), 'goal_x:=10.0', 'assume_bounded_water:=true'], stdout=log, stderr=subprocess.STDOUT)
        rclpy.init()
        node = Fixture()
        node.launch_process = process
        try:
            until(node, lambda: node.x > .5, 45)
            if os.environ.get('NAV2_TEST_SCENARIO') == 'paused_map':
                node.paused = True
                until(node, lambda: node.status.get('stage') == 'fault' and node.speed == 0, 5)
                assert 'Injected permanent pose discontinuity' in node.status['reason'], node.status
                node.paused = False
                deadline = time.monotonic()+2
                until(node, lambda: time.monotonic() > deadline, 3)
                assert node.status['stage'] == 'fault' and node.speed == 0, node.status
                print('PASS: permanent mapper pause latches a terminal stop with its cause', flush=True)
                Path(os.environ.get('NAV2_TEST_RESULTS', '/tmp/nav2-result.json')).write_text(
                    json.dumps(dict(passed=True, final_status=node.status), indent=2)+'\n')
                return
            node.freeze = True
            until(node, lambda: node.status.get('reason') == 'waiting_for_fresh_inputs' and node.speed == 0, 5)
            print('PASS: duplicate map snapshots stop motion despite continued publication', flush=True)
            node.freeze = False
            until(node, lambda: node.x > 1., 20)
            node.blocked = True
            until(node, lambda: node.speed == 0., 8)
            before = node.x
            deadline = time.monotonic()+3
            until(node, lambda: time.monotonic() > deadline, 4)
            assert abs(node.x-before) < .05, 'Blocked route still commanded motion'
            print('PASS: an updated wall across the operating area stops motion', flush=True)
            node.blocked = False
            until(node, lambda: node.status.get('stage') == 'complete', 150)
            if not node.gate:
                assert max(abs(y) for _, y, _ in node.positions) > 1., 'No obstacle detour'
            else:
                assert node.status['events'] == ['gate_a'], node.status
                assert node.x-1.1 > 7., 'Stern did not clear gate'
            clearance = []
            for bx, by in ([(7., -1.5), (7., 1.5)] if node.gate else [(5., 0.)]):
                for x, y, yaw in node.positions:
                    dx, dy = bx-x, by-y
                    f = dx*math.cos(yaw)+dy*math.sin(yaw)
                    l = -dx*math.sin(yaw)+dy*math.cos(yaw)
                    clearance.append(math.hypot(max(abs(f)-1.1, 0), max(abs(l)-.6, 0))-.35)
            assert min(clearance) > 0., min(clearance)
            print(f'PASS: Nav2 {"3m gate" if node.gate else "detour"} completed; minimum physical hull clearance={min(clearance):.3f}m', flush=True)
            node.session = 'integration-reset'
            until(node, lambda: node.status.get('stage') == 'fault' and node.speed == 0, 5)
            print('PASS: mapping session change latches a stop', flush=True)
            Path(os.environ.get('NAV2_TEST_RESULTS', '/tmp/nav2-result.json')).write_text(json.dumps(
                dict(passed=True, minimum_clearance_m=min(clearance), samples=node.positions,
                     paths=node.paths, commands=node.commands,
                     final_status=node.status), indent=2)+'\n')
        except BaseException:
            Path(os.environ.get('NAV2_TEST_RESULTS', '/tmp/nav2-result.json')).write_text(json.dumps(
                dict(passed=False, samples=node.positions, paths=node.paths, commands=node.commands,
                     final_status=node.status), indent=2)+'\n')
            print(log_path.read_text()[-18000:], flush=True)
            raise
        finally:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            node.destroy_node()
            rclpy.try_shutdown()


if __name__ == '__main__':
    main()

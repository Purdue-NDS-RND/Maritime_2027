"""Map-driven Nav2 mission supervisor and independent movement gate."""
from array import array
import copy
import json
import math
import time

import numpy as np
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import TransformStamped, Twist, TwistStamped
from maritime_interfaces.msg import BearingObservationArray, BuoyMap
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry
from std_msgs.msg import String
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from tf2_ros import TransformBroadcaster

from maritime_localization.geometry import rigid_transform
from maritime_navigation.costmap import InputProgress, SnapshotPair, active_bearings, planning_grid, resample_physical, swept_clear, validate_bounds
from maritime_navigation.mission import Landmark, Mission, observation_goals, search_goal


def ns(stamp):
    return stamp.sec*1_000_000_000+stamp.nanosec


class Navigator(Node):
    def __init__(self):
        super().__init__('map_navigator')
        def parameter(name, default):
            return self.declare_parameter(name, default).value
        self.task = parameter('task', 'goal')
        if self.task not in ('goal', 'gate', 'slalom'):
            raise ValueError('Unknown task')
        self.assumed_water = parameter('assume_bounded_water', False)
        self.bootstrap_enabled = parameter('bootstrap_clear_start', False)
        self.bounds = validate_bounds(json.loads(parameter('operating_bounds', '[-5,-12,45,12]')))
        self.sigma = parameter('obstacle_sigma', 2.)
        self.clearance = parameter('obstacle_clearance_m', .15)
        self.planning_resolution = parameter('planning_resolution_m', .1)
        self.uncertainty_mode = parameter('uncertainty_mode', 'graded')
        if (not math.isfinite(self.planning_resolution) or self.planning_resolution <= 0
                or self.uncertainty_mode not in ('graded', 'hard')):
            raise ValueError('Invalid planning resolution or uncertainty policy')
        self.tree = parameter('behavior_tree', '')
        self.goal = tuple(parameter(name, default) for name, default in
                          [('goal_x', 10.), ('goal_y', 0.), ('goal_yaw', 0.)])
        if not all(map(math.isfinite, (*self.goal, self.sigma, self.clearance))) or min(self.sigma, self.clearance) < 0:
            raise ValueError('Invalid goal or clearance')
        self.mission = Mission(turns=0 if self.task == 'gate' else 4)
        self.map = self.physical = self.pose = self.grid = None
        self.progress = InputProgress()
        self.snapshots = SnapshotPair()
        self.source_session = None
        self.source_stamp = 0
        self.source_paused = False
        self.bearings = {}
        self.pose_arrival = self.command_arrival = -math.inf
        self.measured_speed = self.measured_rate = 0.
        self.pose_stamp = 0
        self.raw_command = Twist()
        self.origin = None
        self.resolution = None
        self.start_pose = None
        self.bootstrap_index = 0
        self.observation_target = None
        self.observation_anchor = None
        self.observation_attempts = 0
        self.stage = 'waiting_for_map'
        self.reason = 'waiting_for_inputs'
        self.last_report = None
        self.fault = None
        self.target = None
        self.requested_target = None
        self.send_future = self.goal_handle = self.result_future = self.cancel_future = None
        self.retry_at = 0.
        self.action_failure = None
        self.started = time.monotonic()
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.command = self.create_publisher(TwistStamped, '/navigation/velocity', 10)
        self.status = self.create_publisher(String, '/navigation/status', 10)
        self.planning = self.create_publisher(OccupancyGrid, '/navigation/planning_grid', durable)
        self.odometry = self.create_publisher(Odometry, '/navigation/odometry', 10)
        self.tf = TransformBroadcaster(self)
        self.action = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        self.create_subscription(BuoyMap, '/mapping/buoys', self.on_map, durable)
        self.create_subscription(BearingObservationArray, '/mapping/observations', self.on_bearings, qos_profile_sensor_data)
        self.create_subscription(OccupancyGrid, '/mapping/occupancy_grid', self.on_grid, durable)
        self.create_subscription(Odometry, 'vessel/odometry', self.on_pose, qos_profile_sensor_data)
        self.create_subscription(Twist, '/navigation/cmd_vel', self.on_command, 10)
        self.create_timer(.1, self.tick)

    def on_map(self, message):
        if (message.header.frame_id != 'map' or not message.session_id
                or len(set(message.unresolved_world_ids)) != message.unresolved_count
                or len(message.unresolved_world_ids) != message.unresolved_count
                or any(not identity for identity in message.unresolved_world_ids)):
            self.fault = 'invalid_map_frame_or_session'
            return
        stamp = ns(message.header.stamp)
        if self.source_session is not None and message.session_id != self.source_session:
            self.fault = 'mapping_session_changed'
        if stamp < self.source_stamp:
            self.fault = 'mapping_time_rewound'
        self.source_session, self.source_stamp = message.session_id, stamp
        self.source_paused = message.paused
        if message.paused:
            # Mapper pauses latch until a new session. Waiting here cannot
            # recover; make the failure visible and let the bridge disarm.
            self.fault = 'mapping_paused: '+message.detail
        self.match_snapshot('map', stamp, message)

    def match_snapshot(self, kind, stamp, message):
        paired = self.snapshots.push(kind, stamp, message)
        if paired:
            self.map, self.physical = paired
            self.progress.update(self.map.session_id, ns(self.map.header.stamp), time.monotonic())

    def on_bearings(self, message):
        if message.header.frame_id != 'map':
            self.fault = 'invalid_bearing_frame'
            return
        if self.map and message.session_id != self.map.session_id:
            return
        for observation in message.observations:
            # Ambiguous/unassigned detections still represent a possible hazard.
            identity = observation.world_id or (observation.camera_id+':'+observation.category+':'+
                                                str(round(observation.world_bearing_rad, 1)))
            self.bearings[identity] = (ns(message.header.stamp), observation)
        if len(self.bearings) > 1000:
            self.fault = 'too_many_unresolved_hazards'

    def on_grid(self, message):
        info = message.info
        q = info.origin.orientation
        if (message.header.frame_id != 'map' or not math.isfinite(info.resolution) or info.resolution <= 0
                or not 0 < info.width*info.height <= 4_000_000
                or len(message.data) != info.width*info.height
                or not np.allclose([q.x, q.y, q.z, q.w], [0, 0, 0, 1])
                or not all(map(math.isfinite, [info.origin.position.x, info.origin.position.y]))):
            self.fault = 'invalid_physical_grid'
            return
        self.match_snapshot('grid', ns(message.header.stamp), message)

    def on_pose(self, message):
        if message.header.frame_id != 'map' or message.child_frame_id != 'base_link':
            self.fault = 'invalid_odometry_frame'
            return
        try:
            p = message.pose.pose
            matrix = rigid_transform(p.position, p.orientation)
            if not np.isfinite(message.twist.covariance).all():
                raise ValueError('Nonfinite velocity covariance')
            values = message.twist.twist
            if not all(map(math.isfinite, [values.linear.x, values.linear.y, values.angular.z])):
                raise ValueError('Nonfinite measured velocity')
        except ValueError:
            self.fault = 'invalid_odometry'
            return
        stamp = ns(message.header.stamp)
        if stamp <= self.pose_stamp:
            if stamp < self.pose_stamp:
                self.fault = 'odometry_time_rewound'
            return
        self.pose_stamp = stamp
        self.measured_speed = math.hypot(values.linear.x, values.linear.y)
        self.measured_rate = values.angular.z
        self.pose = (float(matrix[0, 3]), float(matrix[1, 3]), math.atan2(matrix[1, 0], matrix[0, 0]))
        self.pose_arrival = time.monotonic()
        if self.start_pose is None:
            self.start_pose = self.pose
        # Current FCU local estimate is map referenced and has no separate global
        # correction. navigation_odom is explicitly the same coordinate system.
        # Re-stamp live state into the Nav2 wall-clock domain, leaving mapper
        # acquisition-time odometry untouched. This is not a replay interface.
        output = copy.deepcopy(message)
        output.header.stamp = self.get_clock().now().to_msg()
        output.header.frame_id = 'navigation_odom'
        output.pose.pose.position.z = 0.
        output.pose.pose.orientation.x = output.pose.pose.orientation.y = 0.
        output.pose.pose.orientation.z = math.sin(self.pose[2]/2)
        output.pose.pose.orientation.w = math.cos(self.pose[2]/2)
        self.odometry.publish(output)
        transforms = []
        for parent, child, x, y, yaw in [('map', 'navigation_odom', 0., 0., 0.),
                                       ('navigation_odom', 'base_link', *self.pose)]:
            transform = TransformStamped()
            transform.header.stamp = output.header.stamp
            transform.header.frame_id, transform.child_frame_id = parent, child
            transform.transform.translation.x, transform.transform.translation.y = x, y
            transform.transform.rotation.z, transform.transform.rotation.w = math.sin(yaw/2), math.cos(yaw/2)
            transforms.append(transform)
        self.tf.sendTransform(transforms)

    def on_command(self, message):
        values = (message.linear.x, message.linear.y, message.linear.z,
                  message.angular.x, message.angular.y, message.angular.z)
        if (not all(map(math.isfinite, values)) or not 0 <= values[0] <= .5
                or abs(values[-1]) > .5 or any(abs(v) > 1e-6 for v in values[1:5])):
            self.command_arrival = -math.inf
            return
        self.raw_command, self.command_arrival = message, time.monotonic()

    def constraints(self):
        m = self.mission
        if m.forward is None or m.target is None:
            return []
        if m.stage in ('gate_a', 'gate_b'):
            _, centre = m.coordinates(*m.target)
            return [(m.origin, m.forward, m.left, m.gate_plane_s,
                     centre-m.gate_width/2, centre+m.gate_width/2)]
        if m.stage.startswith('turn_'):
            buoy = next((b for b in m.landmarks if b.identity in m.active_ids), None)
            if buoy:
                s, t = m.coordinates(buoy.x, buoy.y)
                low, high = (t+.6, math.inf) if buoy.category == 'red' else (-math.inf, t-.6)
                return [(m.origin, m.forward, m.left, s, low, high)]
        return []

    def select_target(self, now):
        if self.task == 'goal':
            self.stage = 'goal'
            return self.goal
        # Metric positions and persistent identities come solely from shared map.
        stamp = ns(self.map.header.stamp)
        self.mission.landmarks = [Landmark(t.world_id, t.category, t.x, t.y,
            now-max(0., (stamp-ns(t.last_seen))/1e9),
            max(3, t.confirmation_evidence))
            for t in self.map.tracks if t.lifecycle in ('confirmed', 'stale')]
        self.mission.refresh_target()
        survey = observation_goals(*self.start_pose)
        if self.bootstrap_enabled and self.bootstrap_index == 0:
            self.stage = 'bootstrap'
            return survey[0]
        target = self.mission.update(*self.pose, now)
        self.stage = self.mission.stage
        if (self.bootstrap_enabled and not self.mission.events
                and (self.mission.forward is None or
                     (self.uncertainty_mode == 'hard' and self.map.unresolved_count))):
            if self.bootstrap_index < len(survey):
                self.stage = 'bootstrap'
                return survey[self.bootstrap_index]
            self.stage = 'waiting_for_range' if self.map.unresolved_count else self.mission.stage
            return None
        if target:
            self.observation_target = None
            self.observation_anchor = None
            self.observation_attempts = 0
            heading = math.atan2(self.mission.forward[1], self.mission.forward[0])
            return (*target, heading)
        if (self.stage in ('search', 'search_exit') and self.assumed_water
                and self.uncertainty_mode == 'graded'):
            if self.observation_anchor is None:
                self.observation_anchor = self.pose
            if self.observation_target is None:
                self.observation_target = search_goal(self.mission, self.observation_anchor, self.bounds,
                                                       self.observation_attempts)
            if self.observation_target:
                self.stage = 'observe'
                return self.observation_target
            self.stage = 'waiting_for_range'
        return None

    def cancel(self):
        if self.goal_handle and self.cancel_future is None:
            self.cancel_future = self.goal_handle.cancel_goal_async()

    def poll_action(self, now):
        if self.send_future and self.send_future.done():
            self.goal_handle = self.send_future.result()
            self.send_future = None
            if not self.goal_handle.accepted:
                self.goal_handle = None
                self.retry_at = now+2.
                self.action_failure = 'goal_rejected'
            else:
                self.action_failure = None
                self.result_future = self.goal_handle.get_result_async()
        if self.result_future and self.result_future.done():
            result = self.result_future.result()
            succeeded = result.status == GoalStatus.STATUS_SUCCEEDED
            if result.status == GoalStatus.STATUS_ABORTED:
                self.action_failure = ('navigation_failed: '+str(getattr(result.result, 'error_code', 'unknown'))+
                                       ' '+getattr(result.result, 'error_msg', ''))
            if succeeded and self.requested_target == self.target:
                if self.stage == 'bootstrap':
                    self.bootstrap_index += 1
                elif self.task == 'goal':
                    self.stage = 'complete'
            if self.stage == 'observe':
                self.observation_attempts += 1
                self.observation_target = None
            self.goal_handle = self.result_future = self.cancel_future = None
            self.requested_target = None
            self.retry_at = now+(.2 if succeeded else 2.)
            # Never forward a cached command from an old/cancelled action.
            self.command_arrival = -math.inf

    def tick(self):
        now = time.monotonic()
        self.poll_action(now)
        terminal = self.stage in ('complete', 'fault')
        reason = self.fault or self.progress.fault or (self.stage if terminal else None)
        healthy = (not reason and self.map is not None and not self.map.paused and not self.source_paused
                   and self.physical is not None and self.progress.ready(now)
                   and now-self.pose_arrival < .5
                   and ns(self.physical.header.stamp) == ns(self.map.header.stamp))
        if not healthy:
            reason = reason or ('mapping_paused' if self.source_paused else
                'waiting_for_fresh_inputs' if not self.progress.ready(now) else
                'odometry_timeout' if now-self.pose_arrival >= .5 else 'waiting_for_matching_grid')
        if healthy and not terminal:
            self.target = self.select_target(now)
            self.bearings = active_bearings(self.bearings, self.map.tracks,
                                           self.map.unresolved_world_ids, ns(self.map.header.stamp))
            missing_bearings = set(self.map.unresolved_world_ids)-{b.world_id for _, b in self.bearings.values()}
            if missing_bearings and self.stage != 'bootstrap':
                healthy = False
                reason = 'waiting_for_unresolved_bearings'
            info = self.physical.info
            try:
                source, self.origin = resample_physical(
                    np.asarray(self.physical.data).reshape(info.height, info.width),
                    (info.origin.position.x, info.origin.position.y), info.resolution,
                    self.bounds, self.planning_resolution)
                self.resolution = self.planning_resolution
                self.grid = planning_grid(source, self.origin, self.resolution, self.bounds, self.map.tracks, self.sigma,
                    self.clearance, self.assumed_water, self.constraints(),
                    bearings=[b for _, b in self.bearings.values()],
                    clear_start=self.start_pose if self.bootstrap_enabled else None,
                    restrict_to_start=self.stage == 'bootstrap', uncertainty_mode=self.uncertainty_mode)
            except ValueError as error:
                self.fault = 'invalid_map: '+str(error)
                healthy = False
                reason = self.fault
            else:
                output = copy.deepcopy(self.physical)
                output.header.stamp = self.get_clock().now().to_msg()
                output.info.resolution = self.resolution
                output.info.height, output.info.width = self.grid.shape
                output.info.origin.position.x, output.info.origin.position.y = self.origin
                output.data = array('b', self.grid.tobytes())
                self.planning.publish(output)
                if healthy:
                    reason = 'following_path' if self.target else self.stage
        terminal = self.stage in ('complete', 'fault') or bool(self.fault or self.progress.fault)
        if terminal and (self.fault or self.progress.fault):
            self.stage = 'fault'
        # Short telemetry gaps stop commands immediately but need not destroy a
        # valid Nav2 action. Cancel on prolonged loss or invalid map knowledge.
        cancel_inputs = (self.source_paused or not self.progress.ready(now)
                         or now-self.pose_arrival >= 2.)
        if (cancel_inputs or terminal or self.requested_target != self.target):
            self.cancel()
        if (healthy and not terminal and self.target and self.send_future is None and self.goal_handle is None
                and now >= self.retry_at and self.action.server_is_ready()):
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = 'map'
            goal.pose.header.stamp = self.get_clock().now().to_msg()
            goal.pose.pose.position.x, goal.pose.pose.position.y = self.target[:2]
            goal.pose.pose.orientation.z = math.sin(self.target[2]/2)
            goal.pose.pose.orientation.w = math.cos(self.target[2]/2)
            goal.behavior_tree = self.tree
            self.command_arrival = -math.inf
            self.requested_target = self.target
            self.send_future = self.action.send_goal_async(goal)
        message = TwistStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = 'base_link'
        active = healthy and not terminal and self.goal_handle is not None and self.cancel_future is None
        if active and now-self.command_arrival < .3:
            command = self.raw_command
            speed = max(command.linear.x, self.measured_speed)
            # Do not assume the hull immediately achieves requested curvature:
            # include straight coasting and the currently measured turn rate.
            if all(swept_clear(self.grid, self.origin, self.resolution, *self.pose, speed, rate)
                   for rate in (command.angular.z, self.measured_rate, 0.)):
                message.twist = command
            else:
                reason = 'predicted_collision_stop'
        elif healthy and not terminal and self.target:
            reason = self.action_failure or 'waiting_for_path_or_controller'
        self.command.publish(message)
        self.reason = reason
        if self.last_report != (self.stage, reason):
            self.get_logger().info(f'{self.stage}: {reason}; pose_age={now-self.pose_arrival:.2f}s; '
                                   f'map_progress_age={now-self.progress.progress:.2f}s')
            self.last_report = (self.stage, reason)
        observations = {}
        if self.map:
            for track in self.map.tracks:
                for camera in track.source_cameras:
                    observations[camera] = observations.get(camera, 0)+track.observation_count
        self.status.publish(String(data=json.dumps(dict(stage=self.stage, reason=reason,
            ready=bool(healthy and self.target and not terminal and
                       (message.twist.linear.x > 0 or abs(message.twist.angular.z) > 0)), target=self.target,
            events=self.mission.events, observations=observations,
            map_session=self.progress.session, map_stamp_ns=self.progress.stamp,
            unresolved=self.map.unresolved_count if self.map else 0,
            assumed_bounded_water=self.assumed_water, uncertainty_mode=self.uncertainty_mode,
            pose_age_s=now-self.pose_arrival if math.isfinite(self.pose_arrival) else None,
            map_progress_age_s=now-self.progress.progress if math.isfinite(self.progress.progress) else None,
            elapsed=now-self.started))))


def main(args=None):
    rclpy.init(args=args)
    node = Navigator()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if rclpy.ok():
            node.cancel()
            for _ in range(5):
                message = TwistStamped()
                message.header.frame_id = 'base_link'
                node.command.publish(message)
        node.destroy_node()
        rclpy.try_shutdown()

"""RGB-only ROS mapper: one posterior writer for all configured camera streams."""

from collections import Counter
from array import array
from dataclasses import asdict
import json
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from maritime_interfaces.msg import (BearingObservation, BearingObservationArray, BuoyEstimate,
                                     BuoyEstimateArray, BuoyMap, BuoyTrack)
from nav_msgs.msg import OccupancyGrid, Odometry
import numpy as np
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo
from tf2_ros import Buffer, TransformException, TransformListener
from vision_msgs.msg import Detection2DArray
from visualization_msgs.msg import Marker, MarkerArray

from maritime_localization.bearing import Bearing
from maritime_localization.geometry import camera_ray, validate_observation, rigid_transform
from maritime_localization.interfaces import Observation
from maritime_localization.mapping import BearingMapper, MappingSettings
from maritime_localization.timing import PoseBuffer, TimedPose
from maritime_perception.aruco import BoundingBox


def stamp_ns(stamp):
    return stamp.sec*1_000_000_000 + stamp.nanosec


def ros_stamp(value):
    return Time(nanoseconds=int(value)).to_msg()


def positive_covariance(covariance):
    covariance = np.asarray(covariance, dtype=float).reshape(6, 6)
    if (not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T, atol=1e-6)
            or np.linalg.eigvalsh(covariance).min() < -1e-8):
        raise ValueError('Invalid odometry pose covariance')
    return covariance


class BuoyMappingNode(Node):
    def __init__(self):
        super().__init__('buoy_mapper')
        def parameter(name, default):
            return self.declare_parameter(name, default).value
        settings = MappingSettings(**{name: parameter(f'bearing_ekf.{name}', default)
                                      for name, default in asdict(MappingSettings()).items()})
        self.mapper = BearingMapper(settings)
        self.frame = parameter('reference_frame', 'map')
        self.body = parameter('body_frame', 'base_link')
        self.cameras = parameter('cameras', ['camera_0'])
        self.offset_s = parameter('pose_time_offset_s', 0.)
        self.wait_s = parameter('pose_wait_s', .5)
        self.queue_limit = parameter('max_pending_frames', 60)
        self.resolution = parameter('costmap_resolution_m', .5)
        self.extent = parameter('costmap_extent_m', 100.)
        self.map_publish_hz = parameter('map_publish_hz', 10.)
        self.max_pose_gap_s = parameter('max_pose_gap_s', .3)
        if (not self.cameras or len(set(self.cameras)) != len(self.cameras)
                or not np.isfinite([self.offset_s, self.wait_s, self.resolution, self.extent, self.max_pose_gap_s, self.map_publish_hz]).all()
                or min(self.wait_s, self.resolution, self.extent, self.max_pose_gap_s, self.map_publish_hz) <= 0
                or not 1 <= self.queue_limit <= 1000 or self.extent/self.resolution > 2000):
            raise ValueError('Invalid mapper input/timing/grid parameters')
        self.poses = PoseBuffer(max_gap_s=self.max_pose_gap_s)
        self.calibration = {}
        self.mounts = {}
        self.pending = []
        self.last_arrival = None
        self.newest = {}
        self.counters = Counter()
        self.transforms = Buffer()
        self.listener = TransformListener(self.transforms, self)
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.map_publisher = self.create_publisher(BuoyMap, '/mapping/buoys', durable)
        self.grid_publisher = self.create_publisher(OccupancyGrid, '/mapping/occupancy_grid', durable)
        self.legacy_grid_publisher = self.create_publisher(OccupancyGrid, '/mapping/costmap', durable)
        self.marker_publisher = self.create_publisher(MarkerArray, '/mapping/markers', durable)
        self.diagnostic_publisher = self.create_publisher(DiagnosticArray, '/mapping/diagnostics', 10)
        self.observation_publisher = self.create_publisher(BearingObservationArray, '/mapping/observations', qos_profile_sensor_data)
        self.estimate_publisher = self.create_publisher(BuoyEstimateArray, 'buoys', qos_profile_sensor_data)
        self.subscriptions_owned = [self.create_subscription(Odometry, 'vessel/odometry', self.receive_pose, qos_profile_sensor_data)]
        for camera in self.cameras:
            self.subscriptions_owned += [
                self.create_subscription(CameraInfo, f'/sensors/{camera}/color/camera_info',
                                         lambda message, c=camera: self.receive_calibration(c, message), qos_profile_sensor_data),
                self.create_subscription(Detection2DArray, f'/perception/{camera}/detections',
                                         lambda message, c=camera: self.receive(c, message), qos_profile_sensor_data)]
        # Input timeouts must still expire when bag /clock pauses or reaches EOF.
        self.wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.timer = self.create_timer(.02, self.drain, clock=self.wall_clock)
        self.map_timer = self.create_timer(1./self.map_publish_hz, self.publish_map, clock=self.wall_clock)
        self.get_logger().info(f'RGB-only session={self.mapper.session_id}; acquisition-time interpolation; '
                               f'pose stamp + {self.offset_s}s = image stamp; parameters={asdict(settings)}')

    def receive_calibration(self, camera, message):
        previous = self.calibration.get(camera)
        if previous and (previous.header.frame_id != message.header.frame_id or list(previous.k) != list(message.k)
                         or list(previous.d) != list(message.d) or previous.distortion_model != message.distortion_model
                         or previous.width != message.width or previous.height != message.height):
            self.mapper.pause('Camera calibration changed; restart mapping session')
        self.calibration[camera] = message

    def receive_pose(self, message):
        try:
            if message.header.frame_id != self.frame or message.child_frame_id != self.body:
                raise ValueError('Odometry frame/child differs from configured map/body frame')
            pose = message.pose.pose
            covariance = positive_covariance(message.pose.covariance)
            self.poses.add(TimedPose(stamp_ns(message.header.stamp) + int(self.offset_s*1e9),
                                    rigid_transform(pose.position, pose.orientation), covariance))
            if self.poses.fault:
                self.mapper.pause(self.poses.fault)
        except ValueError as error:
            self.mapper.pause(str(error))
        self.drain()

    def receive(self, camera, message):
        stamp = stamp_ns(message.header.stamp)
        self.last_arrival = time.monotonic()
        previous = self.newest.get(camera)
        if previous is not None and stamp < previous:
            self.mapper.pause('Camera clock rewound; restart mapping session')
        self.newest[camera] = stamp
        self.pending.append((stamp, camera, message, time.monotonic()))
        self.pending.sort(key=lambda item: (item[0], item[1]))
        if len(self.pending) > self.queue_limit:
            _, _, dropped, _ = self.pending.pop(0)
            self.counters['queue_overflow'] += 1
            self.publish_status(dropped, 'waiting_for_inputs', 'Pending frame queue overflow')
        self.drain()

    def build(self, camera, message, pose):
        calibration = self.calibration.get(camera)
        if calibration is None:
            raise LookupError('Waiting for camera calibration')
        if calibration.header.frame_id != message.header.frame_id:
            raise ValueError('Detection/calibration optical frame mismatch')
        mount = self.transforms.lookup_transform(self.body, message.header.frame_id, Time()).transform
        mounting = rigid_transform(mount.translation, mount.rotation)
        previous_mount = self.mounts.get(camera)
        if previous_mount is not None and not np.allclose(previous_mount, mounting, atol=1e-7, rtol=0):
            self.mapper.pause('Camera mounting transform changed; restart mapping session')
            raise ValueError(self.mapper.paused_reason)
        self.mounts[camera] = mounting.copy()
        transform = pose.transform @ mounting
        obs = Observation(stamp_ns(message.header.stamp), message.header.frame_id,
                          np.array(calibration.k).reshape(3, 3), tuple(calibration.d),
                          camera_to_reference=transform, reference_frame=self.frame,
                          distortion_model=calibration.distortion_model)
        validate_observation(obs)
        s = self.mapper.settings
        covariance = pose.covariance.copy()
        covariance[:3, :3] += np.eye(3)*s.pose_position_floor_m**2
        covariance[3:, 3:] += np.eye(3)*np.deg2rad(s.pose_attitude_floor_deg)**2
        # Lever-arm uncertainty contributes to camera origin uncertainty.
        lever = pose.transform[:3, :3] @ mounting[:3, 3]
        cross = np.array([[0., -lever[2], lever[1]], [lever[2], 0., -lever[0]], [-lever[1], lever[0], 0.]])
        origin_jacobian = np.column_stack((np.eye(3), -cross))
        origin_covariance = (origin_jacobian @ covariance @ origin_jacobian.T)[:2, :2]
        measurements = []
        for index, detection in enumerate(message.detections):
            if not detection.results:
                continue
            box = BoundingBox(-1, detection.results[0].hypothesis.class_id,
                              detection.bbox.center.position.x, detection.bbox.center.position.y,
                              detection.bbox.size_x, detection.bbox.size_y)
            if not 0 <= box.center_x < calibration.width or not 0 <= box.center_y < calibration.height:
                self.counters['outside_image'] += 1
                continue
            ray = camera_ray(obs, box)
            if ray is None:
                self.counters['invalid_box'] += 1
                continue
            direction = transform[:3, :3] @ (ray/np.linalg.norm(ray))
            horizontal = np.linalg.norm(direction[:2])
            if horizontal < .1:
                self.counters['near_vertical_bearing'] += 1
                continue
            bearing_jacobian = np.array([-direction[1], direction[0], 0.]) / horizontal**2
            direction_cross = np.array([[0., -direction[2], direction[1]],
                                        [direction[2], 0., -direction[0]], [-direction[1], direction[0], 0.]])
            attitude_jacobian = bearing_jacobian @ -direction_cross
            variance = (np.deg2rad(s.bearing_std_deg)**2
                        + float(attitude_jacobian @ covariance[3:, 3:] @ attitude_jacobian))
            # Inflation bounds omitted translation/attitude cross correlation in
            # this independent-pose approximation (Cauchy-Schwarz upper bound).
            measurements.append(Bearing(obs.timestamp_ns, camera, transform[:2, 3].copy(),
                float(np.arctan2(direction[1], direction[0])), 2*variance, 2*origin_covariance,
                box.category, f'{camera}:{obs.timestamp_ns}:{index}'))
        return measurements

    def drain(self):
        while self.pending:
            stamp, camera, message, arrival = self.pending[0]
            if self.mapper.paused_reason:
                self.pending.pop(0)
                self.publish_status(message, 'waiting_for_inputs', self.mapper.paused_reason)
                continue
            try:
                pose, bracket = self.poses.lookup(stamp)
                measurements = self.build(camera, message, pose)
            except (LookupError, TransformException) as error:
                if time.monotonic()-arrival < self.wait_s:
                    break
                self.pending.pop(0)
                self.counters['pose_or_calibration_timeout'] += 1
                self.publish_status(message, 'waiting_for_inputs', str(error))
                continue
            except ValueError as error:
                self.pending.pop(0)
                self.counters['invalid_input'] += 1
                self.publish_status(message, 'waiting_for_inputs', str(error))
                continue
            self.pending.pop(0)
            if self.mapper.last_stamp_ns is not None and stamp < self.mapper.last_stamp_ns:
                self.counters['late_frame_rejected'] += 1
                self.publish_status(message, 'waiting_for_inputs', 'Late frame rejected by ordered-update policy')
                continue
            started = time.monotonic()
            updated = self.mapper.process(stamp, measurements)
            self.counters['last_processing_ms'] = round((time.monotonic()-started)*1000, 3)
            self.counters['frames_ready'] += 1
            self.publish_status(message, 'ok', 'Acquisition-time pose; RGB bearings only', updated, pose.stamp_ns)
            observations = BearingObservationArray()
            observations.header.stamp, observations.header.frame_id = message.header.stamp, self.frame
            observations.session_id = self.mapper.session_id
            observations.pose_before = ros_stamp(bracket[0]-int(self.offset_s*1e9))
            observations.pose_after = ros_stamp(bracket[1]-int(self.offset_s*1e9))
            observations.pose_time_offset_s = self.offset_s
            for view, identity, decision in self.mapper.decisions:
                observations.observations.append(BearingObservation(observation_id=view.observation_id,
                    camera_id=camera, category=view.category, origin_x=float(view.origin[0]),
                    origin_y=float(view.origin[1]), world_bearing_rad=view.angle,
                    bearing_variance=view.variance, world_id=identity, decision=decision))
            self.observation_publisher.publish(observations)

    def publish_status(self, message, status, detail, updated=(), pose_ns=0):
        output = BuoyEstimateArray(method='bearing_ekf', status=status, detail=detail, inputs_ready=status == 'ok')
        output.header.stamp, output.header.frame_id = message.header.stamp, self.frame
        output.vessel_pose_stamp = ros_stamp(pose_ns-int(self.offset_s*1e9) if pose_ns else 0)
        for track in updated:
            if track.state == 'confirmed':
                output.estimates.append(BuoyEstimate(category=track.category, track_id=track.identifier,
                                                     x=float(track.mean[0]), y=float(track.mean[1])))
        self.estimate_publisher.publish(output)

    def publish_map(self):
        stamp = self.mapper.last_stamp_ns or 0
        output = BuoyMap(session_id=self.mapper.session_id, paused=bool(self.mapper.paused_reason),
                         detail=self.mapper.paused_reason or '')
        output.header.frame_id, output.header.stamp = self.frame, ros_stamp(stamp)
        output.unresolved_count = sum(track.mean is None for track in self.mapper.tracks)
        for track in self.mapper.snapshot():
            age = max(0., (stamp-track.last_seen_ns)/1e9)
            confidence = min(1., track.confirmation_evidence/self.mapper.settings.confirmation_updates)*np.exp(-age/60.)
            output.tracks.append(BuoyTrack(world_id=track.identifier, category=track.category,
                category_probability=1., lifecycle=track.state, x=float(track.mean[0]), y=float(track.mean[1]),
                covariance=track.covariance.reshape(-1).tolist(), footprint_radius_m=self.mapper.settings.footprint_radius_m,
                existence_confidence=float(confidence), first_seen=ros_stamp(track.first_seen_ns),
                last_seen=ros_stamp(track.last_seen_ns), last_update=ros_stamp(track.last_update_ns),
                source_cameras=sorted(track.cameras), observation_count=track.observations,
                selected_observation_count=track.selected_observations, confirmation_evidence=track.confirmation_evidence,
                observation_ids=track.provenance, last_residual_rad=track.residual_rad))
        self.map_publisher.publish(output)
        # Rebuild occupancy from current estimates, removing old footprints after
        # refinement. No free-water evidence is inferred from RGB detections.
        grid = OccupancyGrid(header=output.header)
        cells = int(np.ceil(self.extent/self.resolution))
        grid.info.resolution, grid.info.width, grid.info.height = float(self.resolution), cells, cells
        grid.info.origin.position.x = grid.info.origin.position.y = -self.extent/2
        grid.info.origin.orientation.w = 1.
        data = np.full((cells, cells), -1, dtype=np.int8)
        markers = MarkerArray(markers=[Marker(action=Marker.DELETEALL)])
        for index, track in enumerate(output.tracks):
            if track.lifecycle in ('confirmed', 'stale', 'inconsistent'):
                radius = track.footprint_radius_m
                x, y = track.x + self.extent/2, track.y + self.extent/2
                left, right = max(0, int((x-radius)/self.resolution)), min(cells, int((x+radius)/self.resolution)+1)
                bottom, top = max(0, int((y-radius)/self.resolution)), min(cells, int((y+radius)/self.resolution)+1)
                if left < right and bottom < top:
                    yy, xx = np.ogrid[bottom:top, left:right]
                    # Occupy cells touched by the physical disc. Testing only
                    # cell centres can erase small buoys between coarse cells.
                    # Covariance and navigation clearance belong downstream.
                    dx = np.maximum(np.abs((xx+.5)*self.resolution-x)-self.resolution/2, 0.)
                    dy = np.maximum(np.abs((yy+.5)*self.resolution-y)-self.resolution/2, 0.)
                    mask = dx**2 + dy**2 <= radius**2
                    data[bottom:top, left:right][mask] = 100
            marker = Marker(header=output.header, ns='buoys', id=2*index, type=Marker.SPHERE, action=Marker.ADD)
            marker.pose.position.x, marker.pose.position.y = track.x, track.y
            marker.pose.orientation.w = 1.
            values, vectors = np.linalg.eigh(np.array(track.covariance).reshape(2, 2))
            yaw = np.arctan2(vectors[1, 1], vectors[0, 1])
            marker.pose.orientation.z, marker.pose.orientation.w = float(np.sin(yaw/2)), float(np.cos(yaw/2))
            marker.scale.x, marker.scale.y, marker.scale.z = float(6*np.sqrt(values[1])), float(6*np.sqrt(values[0])), .1
            marker.color.r, marker.color.g, marker.color.b, marker.color.a = .9, .6, .1, .5
            markers.markers.append(marker)
            label = Marker(header=output.header, ns='buoys', id=2*index+1, type=Marker.TEXT_VIEW_FACING, action=Marker.ADD)
            label.pose.position.x, label.pose.position.y, label.pose.position.z = track.x, track.y, .5
            label.pose.orientation.w, label.scale.z = 1., .3
            label.color.r = label.color.g = label.color.b = label.color.a = 1.
            label.text = f'{track.world_id} {track.category} {track.lifecycle}'
            markers.markers.append(label)
        grid.data = array('b', data.tobytes())
        self.grid_publisher.publish(grid)
        self.legacy_grid_publisher.publish(grid)
        self.marker_publisher.publish(markers)
        counters = dict(self.counters + self.mapper.diagnostics)
        stale_inputs = self.last_arrival is None or time.monotonic()-self.last_arrival > 2.
        counters['stale_image_input'] = stale_inputs
        counters['pending_frames'] = len(self.pending)
        counters['pose_buffer_samples'] = len(self.poses.samples)
        counters.update({f'tracks_{state}': sum(track.state == state for track in self.mapper.tracks)
                         for state in ('unresolved', 'tentative', 'confirmed', 'stale', 'inconsistent')})
        diagnostics = DiagnosticStatus(name='bearing_ekf_buoy_mapping', hardware_id=self.mapper.session_id,
            level=(DiagnosticStatus.ERROR if self.mapper.paused_reason else
                   DiagnosticStatus.WARN if stale_inputs else DiagnosticStatus.OK),
            message=self.mapper.paused_reason or 'RGB-only independent-landmark mapping',
            values=[KeyValue(key=key, value=json.dumps(value)) for key, value in sorted(counters.items())])
        self.diagnostic_publisher.publish(DiagnosticArray(header=output.header, status=[diagnostics]))


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BuoyMappingNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

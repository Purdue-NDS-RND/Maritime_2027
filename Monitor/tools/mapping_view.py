"""Read-only live mapping evaluation: truth never enters the localization pipeline."""
import argparse
from collections import defaultdict, deque
import math
import re
import time

import numpy as np
import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Point
from maritime_interfaces.msg import BuoyMap
from maritime_localization.geometry import rigid_transform
from maritime_localization.timing import PoseBuffer, TimedPose
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from visualization_msgs.msg import Marker, MarkerArray

from live_geometry import DisplayAlignment, ellipse, ns, yaw

BUOY = re.compile(r'^/blueboat/ground_truth/([a-z][a-z0-9_]*)/odometry$')
COLORS = {'red': 'tab:red', 'green': 'tab:green', 'blue': 'tab:blue', 'white': 'gray'}
RGB = {'red': (1., .15, .15), 'green': (.1, .8, .1), 'blue': (.1, .4, 1.), 'white': (.8, .8, .8)}


class MappingView(Node):
    def __init__(self, pose_topic, offset=0., clock='receipt'):
        super().__init__('monitor_live_mapping_view')
        self.offset = round(offset*1e9)
        self.clock_mode = clock
        self.mapping = None
        self.map_arrival = 0.
        self.truth = {}
        self.truth_arrivals = {}
        self.truth_poses = PoseBuffer(history_s=15.)
        self.alignment = DisplayAlignment()
        self.boat = None
        self.path = deque(maxlen=1500)
        self.history = defaultdict(lambda: deque(maxlen=600))
        self.session = None
        self.diagnostic = 'Waiting for mapper diagnostics'
        self.clock_detail = 'Source stamps + explicit offset' if clock == 'source' else 'Waiting for clock adapter'
        self.alignment_residual = None
        self.owned = {}
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.overlay = self.create_publisher(MarkerArray, '/monitor/mapping/markers', durable)
        self.create_subscription(BuoyMap, '/mapping/buoys', self.on_map, durable)
        self.create_subscription(Odometry, pose_topic, self.on_pose, qos_profile_sensor_data)
        self.create_subscription(Odometry, '/blueboat/ground_truth/odometry', self.on_truth_pose, qos_profile_sensor_data)
        self.create_subscription(DiagnosticArray, '/mapping/diagnostics', self.on_diagnostic, 10)
        if clock == 'receipt':
            self.create_subscription(DiagnosticArray, '/monitor/mapping/clock', self.on_clock_status, 10)
        self.create_timer(1., self.discover)
        self.create_timer(.5, self.publish_overlay)

    def on_diagnostic(self, message):
        for status in message.status:
            if status.name == 'rgb_buoy_mapping':
                counters = {item.key: item.value for item in status.values}
                self.diagnostic = (status.message + '\n'
                    + '  '.join(f'{key}={counters.get(key, "0")}' for key in
                                ('frames', 'tracks_unresolved', 'initialized', 'ekf_update', 'stale_image_input')))

    def on_clock_status(self, message):
        if message.status:
            self.clock_detail = message.status[0].message

    def on_truth_pose(self, message):
        if message.header.frame_id not in ('world', 'odom'):
            return
        pose = message.pose.pose
        self.truth_poses.add(TimedPose(ns(message.header.stamp),
            rigid_transform(pose.position, pose.orientation), np.zeros((6, 6))))
        if self.truth_poses.fault:
            self.alignment = DisplayAlignment()

    def on_pose(self, message):
        if message.header.frame_id != 'map' or message.child_frame_id != 'base_link':
            self.diagnostic = 'Viewer requires map -> base_link vessel odometry'
            return
        p = message.pose.pose
        xy = np.array([p.position.x, p.position.y])
        self.boat = (xy, yaw(p.orientation))
        self.path.append(xy)
        try:
            truth, _ = self.truth_poses.lookup(ns(message.header.stamp)+self.offset)
        except (LookupError, ValueError):
            return
        world_xy = truth.transform[:2, 3]
        world_yaw = math.atan2(truth.transform[1, 0], truth.transform[0, 0])
        if self.alignment.r is None:
            self.alignment.set(world_xy, world_yaw, xy, self.boat[1])
            self.get_logger().warning('Truth display alignment frozen from a matched boat-pose pair; '
                                      'provisional SE(2), not a surveyed accuracy reference')
        self.alignment_residual = float(np.linalg.norm(self.alignment.point(world_xy)-xy))

    def on_map(self, message):
        if message.header.frame_id != 'map':
            self.diagnostic = 'Unsupported map frame for viewer'
            return
        if self.session != message.session_id:
            self.history.clear()
            self.session = message.session_id
        self.mapping = message
        self.map_arrival = time.monotonic()
        for track in message.tracks:
            history = self.history[track.world_id]
            stamp = ns(message.header.stamp)/1e9
            if not history or stamp > history[-1][0]:
                history.append((stamp, track.x, track.y, track.covariance[0], track.covariance[3]))

    def discover(self):
        for topic, types in self.get_topic_names_and_types():
            match = BUOY.fullmatch(topic)
            if match and 'nav_msgs/msg/Odometry' in types and topic not in self.owned:
                name = match[1]
                self.owned[topic] = self.create_subscription(Odometry, topic,
                    lambda message, name=name: self.on_buoy(name, message), qos_profile_sensor_data)

    def on_buoy(self, name, message):
        if message.header.frame_id not in ('world', 'odom'):
            return
        p = message.pose.pose.position
        self.truth[name] = np.array([p.x, p.y])
        self.truth_arrivals[name] = time.monotonic()

    def publish_overlay(self):
        # Only private visualization messages in world. Never publish map->world
        # or modify public TF to force estimates and truth into agreement.
        markers = [Marker(action=Marker.DELETEALL)]
        if self.mapping and self.alignment.r is not None:
            for index, track in enumerate(self.mapping.tracks):
                mean = np.array([track.x, track.y])
                points = ellipse(mean, track.covariance)
                world = self.alignment.r.T @ (points-self.alignment.t[:, None])
                marker = Marker(ns='rgb_estimates', id=3*index, type=Marker.LINE_STRIP)
                marker.header.frame_id = 'world'
                marker.pose.orientation.w = 1.
                marker.scale.x = .04
                marker.color.r, marker.color.g, marker.color.b = RGB.get(track.category, (.8, .6, .1))
                marker.color.a = .9
                marker.lifetime.sec = 2
                marker.points = [Point(x=float(x), y=float(y), z=.8) for x, y in world.T]
                markers.append(marker)
                location = self.alignment.r.T @ (mean-self.alignment.t)
                label = Marker(ns='rgb_estimates', id=3*index+1, type=Marker.TEXT_VIEW_FACING)
                label.header.frame_id = 'world'
                label.pose.position = Point(x=float(location[0]), y=float(location[1]), z=1.2)
                label.pose.orientation.w = 1.
                label.scale.z = .25
                label.color.r = label.color.g = label.color.b = label.color.a = 1.
                label.text = f'{track.world_id} {track.lifecycle} (3 sigma, provisional alignment)'
                label.lifetime.sec = 2
                markers.append(label)
                centre = Marker(ns='rgb_estimates', id=3*index+2, type=Marker.SPHERE)
                centre.header.frame_id = 'world'
                centre.pose.position = Point(x=float(location[0]), y=float(location[1]), z=.8)
                centre.pose.orientation.w = 1.
                centre.scale.x = centre.scale.y = centre.scale.z = .15
                centre.color = marker.color
                centre.lifetime.sec = 2
                markers.append(centre)
        self.overlay.publish(MarkerArray(markers=markers))


class Plot:
    def __init__(self, node):
        import matplotlib.pyplot as plt
        self.plt, self.node = plt, node
        self.figure = plt.figure(figsize=(13, 8))
        self.figure.canvas.manager.set_window_title('Live RGB buoy mapping')
        grid = self.figure.add_gridspec(2, 2, width_ratios=(1.5, 1.))
        self.map = self.figure.add_subplot(grid[:, 0])
        self.mean = self.figure.add_subplot(grid[0, 1])
        self.variance = self.figure.add_subplot(grid[1, 1])
        self.auto = True
        self.figure.canvas.mpl_connect('key_press_event', self.key)

    def key(self, event):
        if event.key == 'a':
            self.auto = not self.auto

    def draw(self):
        n, ax = self.node, self.map
        limits = ax.get_xlim(), ax.get_ylim()
        for axis in (ax, self.mean, self.variance):
            axis.clear()
            axis.grid(alpha=.2)
        ax.set(xlabel='map X (m)', ylabel='map Y (m)', aspect='equal')
        ax.set_title('Buoy means, trails and 3-sigma covariance ellipses\n'
                     'a: toggle auto bounds | toolbar: zoom/pan')
        if n.path:
            path = np.array(n.path)
            ax.plot(path[:, 0], path[:, 1], color='.4', lw=1, label='Boat path')
        if n.boat:
            xy, heading = n.boat
            ax.plot(*xy, 'ko', label='Boat (mapper pose)')
            ax.arrow(*xy, math.cos(heading), math.sin(heading), width=.05, color='black')
        if n.alignment.r is not None:
            for name, position in n.truth.items():
                xy = n.alignment.point(position)
                ax.plot(*xy, marker='x', ms=9, color='black')
                age = time.monotonic()-n.truth_arrivals[name]
                ax.annotate(name + (' [old]' if age > 2 else ''), xy, xytext=(4, -12),
                            textcoords='offset points', fontsize=8)
            ax.plot([], [], 'kx', label='Truth (provisional alignment)')
        tracks = n.mapping.tracks if n.mapping else []
        for track in tracks:
            color = COLORS.get(track.category, 'tab:orange')
            xy = np.array([track.x, track.y])
            line = ellipse(xy, track.covariance)
            ax.plot(*line, color=color, ls='--' if track.lifecycle != 'confirmed' else '-')
            ax.plot(*xy, 'o', color=color, label=f'{track.world_id} {track.category} {track.lifecycle}')
            ax.annotate(track.world_id, xy, xytext=(5, 5), textcoords='offset points', fontsize=9)
            history = np.array(n.history[track.world_id])
            if len(history):
                ax.plot(history[:, 1], history[:, 2], color=color, alpha=.5, lw=1)
                t = history[:, 0]-history[0, 0]
                for column, label, style in ((1, 'X', '-'), (2, 'Y', '--')):
                    self.mean.plot(t, history[:, column], color=color, ls=style,
                                   label=f'{track.world_id} {label}')
                for column, label, style in ((3, 'var X', '-'), (4, 'var Y', '--')):
                    self.variance.plot(t, history[:, column], color=color, ls=style,
                                       label=f'{track.world_id} {label}')
        if not self.auto:
            ax.set_xlim(limits[0])
            ax.set_ylim(limits[1])
        elif not n.path and not tracks:
            ax.set_xlim(-10, 10)
            ax.set_ylim(-10, 10)
        self.mean.set(title='Estimated mean over time', xlabel='seconds since first metric estimate', ylabel='position (m)')
        self.variance.set(title='Estimated marginal variance (not measured error)',
                          xlabel='seconds since first metric estimate', ylabel='variance (m²)')
        for axis in (ax, self.mean, self.variance):
            if axis.get_legend_handles_labels()[0]:
                axis.legend(loc='best', fontsize=7)
        detail = n.diagnostic
        if not n.mapping:
            detail = 'Waiting for /mapping/buoys; start the pipeline and move the boat.'
        elif n.mapping.paused:
            detail = 'MAPPING PAUSED: '+n.mapping.detail
        elif time.monotonic()-n.map_arrival > 2.:
            detail = 'MAP INPUT STALE: last result retained.\n'+detail
        alignment = ('Truth overlay waiting for time-matched boat poses' if n.alignment.r is None else
                     f'Provisional frozen truth alignment; boat discrepancy {n.alignment_residual:.2f} m')
        self.figure.suptitle('RGB-only mapping | '+detail, fontsize=10)
        if not hasattr(self, 'footer'):
            self.footer = self.figure.text(.02, .015, '', fontsize=8)
        self.footer.set_text(n.clock_detail+'\n'+alignment)
        self.figure.tight_layout(rect=(0, .07, 1, .88))
        self.figure.canvas.draw_idle()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pose-topic', default='/monitor/mapping/vessel/odometry')
    parser.add_argument('--offset', type=float, default=0.)
    parser.add_argument('--clock', default='receipt')
    parser.add_argument('--no-window', action='store_true')
    parser.add_argument('--snapshot', help='Save one plot after --snapshot-delay seconds and exit')
    parser.add_argument('--snapshot-delay', type=float, default=3.)
    args = parser.parse_args()
    rclpy.init()
    node = MappingView(args.pose_topic, args.offset, args.clock)
    try:
        if args.no_window and not args.snapshot:
            rclpy.spin(node)
        else:
            import matplotlib
            matplotlib.use('Agg' if args.snapshot else 'TkAgg')
            plot = Plot(node)
            start, last_draw = time.monotonic(), 0.
            while rclpy.ok():
                rclpy.spin_once(node, timeout_sec=.01)
                now = time.monotonic()
                if now-last_draw > .5:
                    plot.draw()
                    last_draw = now
                if args.snapshot and now-start >= args.snapshot_delay:
                    plot.draw()
                    plot.figure.savefig(args.snapshot)
                    break
                if not args.snapshot:
                    plot.plt.pause(.01)
                    if not plot.plt.fignum_exists(plot.figure.number):
                        break
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

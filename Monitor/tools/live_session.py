"""Supervise only the optional mapping processes; never start/stop Simulation."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('run', 'view', 'test'))
    parser.add_argument('--clock', choices=('receipt', 'source'), default='receipt')
    parser.add_argument('--pose-topic', default='/mavros/local_position/odom')
    parser.add_argument('--offset', type=float, default=0.)
    parser.add_argument('--no-window', action='store_true')
    args = parser.parse_args()
    if args.action == 'test':
        os.execvp('python3', ['python3', '-m', 'unittest', 'discover', '-s', '/opt/live-tests',
                             '-p', 'test_live_*.py', '-v'])
    if not args.no_window:
        import tkinter
        try:
            root = tkinter.Tk()
            root.withdraw()
            root.destroy()
        except tkinter.TclError as error:
            print(f'ERROR: popup display unavailable ({error}); check DISPLAY/XAUTHORITY or use VIEW=none', flush=True)
            return 2
    if args.action == 'run':
        import rclpy
        rclpy.init()
        probe = rclpy.create_node('live_mapping_preflight')
        try:
            deadline = time.monotonic()+1.5
            while time.monotonic() < deadline:
                rclpy.spin_once(probe, timeout_sec=.1)
            active = [(name, namespace) for name, namespace in probe.get_node_names_and_namespaces()
                      if (name == 'buoy_mapper' and namespace == '/localization')
                      or (name == 'aruco_detector' and namespace.startswith('/perception/camera_'))]
            if active:
                print(f'ERROR: mapping/detection already active on this domain: {active}', flush=True)
                return 2
        finally:
            probe.destroy_node()
            rclpy.shutdown()
    pose = '/monitor/mapping/vessel/odometry' if args.clock == 'receipt' else args.pose_topic
    commands = []
    if args.action == 'run':
        if args.clock == 'receipt':
            commands.append(['python3', '/opt/live/live_clock.py', '--pose-topic', args.pose_topic])
        # FCU SYSTEM_TIME can arrive at 1 Hz. Wait for the next enclosing reference
        # without changing the production default or allowing pose extrapolation.
        Path('/tmp/live-mapper.yaml').write_text('/localization/buoy_mapper:\n'
            '  ros__parameters:\n    pose_wait_s: 2.0\n')
        commands.append(['ros2', 'launch', 'maritime_localization', 'pipeline.launch.py',
                         'method:=bearing_ekf', 'use_sim_time:=true', 'publish_debug_image:=true',
                         f'pose_topic:={pose}', f'pose_time_offset_s:={args.offset}',
                         'mapper_parameters:=/tmp/live-mapper.yaml'])
    viewer = ['python3', '/opt/live/mapping_view.py', '--pose-topic', pose,
              '--offset', str(args.offset), '--clock', args.clock]
    # Matplotlib redraws must not block occupancy delivery or alignment inputs.
    commands.append([*viewer, '--no-window'])
    if not args.no_window:
        commands.append([*viewer, '--plot-only'])
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    result = 0
    try:
        for command in commands:
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stopping:
            for child in children:
                if child.poll() is not None:
                    result = child.returncode
                    stopping = True
                    break
            time.sleep(.1)
    finally:
        for child in children:
            if child.poll() is None:
                # ros2 launch forwards SIGINT to its nodes. Sending to its whole
                # group would deliver it twice during node teardown.
                child.send_signal(signal.SIGINT)
        deadline = time.monotonic()+8.
        for child in children:
            try:
                child.wait(timeout=max(.1, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    return result


if __name__ == '__main__':
    sys.exit(main())

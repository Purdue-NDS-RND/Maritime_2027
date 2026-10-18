#!/usr/bin/env python3
"""Run map-based Nav2 navigation against a separately started simulator."""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import signal
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'maritime-autonomy-nav2:jazzy'


def session_exit(processes, evaluate):
    """A successful judge may finish before the bridge verifies disarming."""
    ended = {name: process.poll() for name, process in processes.items() if process.poll() is not None}
    if not ended:
        return None
    for name, code in ended.items():
        if name not in ('bridge', 'judge'):
            print(f'Navigation component exited unexpectedly: {name} ({code})', flush=True)
            return code or 1
    if 'judge' in ended:
        if ended['judge']:
            return ended['judge']
        return processes['bridge'].wait(timeout=25) if 'bridge' in processes else 0
    code = ended['bridge']
    return code or (processes['judge'].wait(timeout=15) if evaluate else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'run', 'test'])
    parser.add_argument('--task', choices=['goal', 'gate', 'slalom'], default='slalom')
    parser.add_argument('--goal', nargs=3, type=float, metavar=('X', 'Y', 'YAW'), default=[10., 0., 0.])
    parser.add_argument('--operating-bounds', nargs=4, type=float, default=[-5., -12., 45., 12.],
                        metavar=('XMIN', 'YMIN', 'XMAX', 'YMAX'))
    parser.add_argument('--assume-bounded-water', action='store_true',
                        help='Explicitly permit unknown water only inside the configured operating area')
    parser.add_argument('--bootstrap-clear-start', action='store_true',
                        help='Declare the initial body-relative rectangle [-3,-4,5,4] clear for a bounded observation leg')
    parser.add_argument('--external-map', action='store_true', help='Use an already running shared mapping pipeline')
    parser.add_argument('--uncertainty-mode', choices=['graded', 'hard'], default='graded',
                        help='Graded uncertainty costs (default) or a hard two-sigma exclusion envelope')
    parser.add_argument('--plan-only', action='store_true', help='Do not start the vehicle command/arming bridge')
    parser.add_argument('--evaluate', action='store_true')
    parser.add_argument('--mission-timeout', type=float,
                        help='Wall seconds after arming: default 1200 for slalom, 600 otherwise')
    args = parser.parse_args()
    if args.mission_timeout is None:
        args.mission_timeout = 1200. if args.task == 'slalom' else 600.
    if not math.isfinite(args.mission_timeout) or not 60 <= args.mission_timeout <= 3600:
        parser.error('--mission-timeout must be 60..3600 seconds')
    if args.evaluate and args.task == 'goal':
        parser.error('--evaluate judges gate/slalom courses; omit it for a single goal')
    if args.action == 'build':
        subprocess.run(['make', '-C', str(ROOT/'Simulation'), 'validate'], check=True)
        subprocess.run(['docker', 'build', '-t', IMAGE, '-f',
                        str(ROOT/'autonomy/container/Dockerfile'), str(ROOT/'autonomy')], check=True)
        subprocess.run(['docker', 'build', '-t', 'maritime-sim-evaluation:jazzy', '-f',
                        str(ROOT/'Simulation/tests/evaluation/container/Dockerfile'),
                        str(ROOT/'Simulation/tests/evaluation')], check=True)
        return
    autonomy_image = subprocess.check_output(
        ['docker', 'image', 'inspect', '--format', '{{.Id}}', IMAGE], text=True).strip()
    if args.action == 'test':
        results = ROOT/'Simulation/logs/nav2-validation'
        results.mkdir(parents=True, exist_ok=True)
        subprocess.run(['python3', '-m', 'unittest', 'discover', '-s', str(ROOT/'autonomy/tests'), '-v'], check=True)
        subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                        '-v', f'{ROOT}/Simulation/scripts:/navigation-scripts:ro',
                        '-v', f'{ROOT}/Simulation/tests/evaluation:/tests:ro',
                        'maritime-sim-evaluation:jazzy', 'python3', '-m', 'unittest', 'discover',
                        '-s', '/tests', '-p', 'test_navigation_bridge.py', '-v'], check=True)
        for scenario, domain, filename in [('goal', 97, 'integration.json'), ('gate', 98, 'gate-integration.json')]:
            subprocess.run(['docker', 'run', '--rm', '--network', 'host', '-e', f'ROS_DOMAIN_ID={domain}',
                            '-e', f'NAV2_TEST_SCENARIO={scenario}',
                            '-e', f'NAV2_TEST_RESULTS=/results/{filename}',
                            '-v', f'{results}:/results',
                            '-v', f'{ROOT}/autonomy/tests:/tests:ro', autonomy_image,
                            'bash', '-lc', 'source /etc/maritime_autonomy_setup.bash && '
                            'python3 /tests/nav2_integration.py'], check=True)
        return
    if (not all(map(math.isfinite, args.goal+args.operating_bounds))
            or args.operating_bounds[0] >= args.operating_bounds[2]
            or args.operating_bounds[1] >= args.operating_bounds[3]):
        parser.error('Goal and operating bounds must be finite and ordered')
    domain = int(os.environ.get('ROS_DOMAIN_ID', '0'))
    if not 0 <= domain <= 232:
        parser.error('ROS_DOMAIN_ID must be 0..232')
    if args.bootstrap_clear_start and not args.assume_bounded_water:
        parser.error('Bootstrap requires --assume-bounded-water')
    for name in ['ardupilot-blueboat-sim', 'maritime-sim-adapter']:
        health = subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Health.Status}}', name], text=True).strip()
        if health != 'healthy':
            parser.error(f'{name} is {health}; start Simulation separately')
    for suffix in ['navigator', 'bridge', 'judge', 'mapping', 'clock']:
        if subprocess.run(['docker', 'inspect', 'maritime-nav-'+suffix],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            parser.error('An existing navigation session is present; stop it before starting another')
    # Check ROS participants too, so differently named containers cannot duplicate
    # the mapper or race the actuator command publisher.
    common = ['docker', 'run', '--rm', '--init', '--network', 'host',
              '-e', f'ROS_DOMAIN_ID={domain}', '-e', 'PYTHONDONTWRITEBYTECODE=1',
              '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'OMP_NUM_THREADS=1',
              '-e', 'FASTRTPS_DEFAULT_PROFILES_FILE=/etc/navigation-fastdds.xml',
              '-v', f'{ROOT}/Monitor/config/fastdds.xml:/etc/navigation-fastdds.xml:ro']
    output_probe = subprocess.check_output(common+['-v', f'{ROOT}/autonomy/tools/navigation_preflight.py:/preflight.py:ro',
        autonomy_image, 'bash', '-lc', 'source /etc/maritime_autonomy_setup.bash && python3 /preflight.py'], text=True)
    discovered = json.loads(next(line.removeprefix('PREFLIGHT:') for line in output_probe.splitlines()
                                 if line.startswith('PREFLIGHT:')))
    if (set(discovered['nodes']) & {'map_navigator', 'gate_slalom_navigator', 'controller_server', 'simulation_navigation_bridge'}
            or discovered['publishers'] or ('buoy_mapper' in discovered['nodes'] and not args.external_map)):
        parser.error('Conflicting navigation, actuator publisher or mapper on this ROS domain')
    roster = discovered['roster']
    cameras = roster.get('enabled_cameras') if isinstance(roster, dict) else ['camera_0']
    if (not isinstance(cameras, list) or not 1 <= len(cameras) <= 2
            or not all(isinstance(c, str) and re.fullmatch(r'camera_\d+', c) for c in cameras)
            or len(set(cameras)) != len(cameras)
            or (roster is not None and (not isinstance(roster, dict) or roster.get('schema_version') != 1))):
        parser.error('Invalid Adapter camera roster')
    output = ROOT/'Simulation/logs'/('navigation-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    (output/'settings.json').write_text(json.dumps(
        dict(vars(args), cameras=cameras, autonomy_image=autonomy_image), indent=2)+'\n')
    print(f'Navigation logs: {output}; cameras: {cameras}', flush=True)
    print(f'Unknown-water assumption: {args.assume_bounded_water}; operating bounds: {args.operating_bounds}', flush=True)
    commands = []
    if not args.external_map:
        commands.append(('clock', 'maritime-sim-evaluation:jazzy', ['python3', '/navigation_clock.py'],
                         ['-v', f'{ROOT}/Simulation/scripts/navigation_clock.py:/navigation_clock.py:ro',
                          '-v', f'{ROOT}/Monitor/tools:/clock-tools:ro']))
        mapper_config = output/'mapper.yaml'
        mapper_config.write_text('/localization/buoy_mapper:\n  ros__parameters:\n    pose_wait_s: 2.0\n    costmap_resolution_m: 0.25\n')
        mapping_launch = ['ros2', 'launch', 'maritime_localization', 'pipeline.launch.py',
            'use_sim_time:=true', 'pose_topic:=/navigation/mapping_odometry',
            'mapper_parameters:=/mapper.yaml', 'camera_layout:=single', f'camera:={cameras[0]}']
        if len(cameras) == 2:
            mapping_launch.append(f'second_camera:={cameras[1]}')
        commands.append(('mapping', autonomy_image, ['bash', '-lc',
            'source /etc/maritime_autonomy_setup.bash && exec "$@"', '--', *mapping_launch],
            ['-v', f'{mapper_config}:/mapper.yaml:ro']))
    launch = ['ros2', 'launch', 'maritime_navigation', 'navigation.launch.py',
              f'task:={args.task}', 'pose_topic:=/mavros/local_position/odom',
              f'uncertainty_mode:={args.uncertainty_mode}',
              f'assume_bounded_water:={str(args.assume_bounded_water).lower()}',
              f'bootstrap_clear_start:={str(args.bootstrap_clear_start).lower()}',
              'operating_bounds:='+json.dumps(args.operating_bounds, separators=(',', ':')),
              f'goal_x:={args.goal[0]}', f'goal_y:={args.goal[1]}', f'goal_yaw:={args.goal[2]}']
    commands.append(('navigator', autonomy_image,
        ['bash', '-lc', 'source /etc/maritime_autonomy_setup.bash && exec "$@"', '--', *launch], []))
    if args.evaluate:
        commands.append(('judge', 'maritime-sim-evaluation:jazzy', ['python3', '/navigation_evaluate.py'],
                         ['-e', f'NAVIGATION_MISSION_TIMEOUT_S={args.mission_timeout}',
                          '-v', f'{ROOT}/Simulation/tests/evaluation/navigation_evaluate.py:/navigation_evaluate.py:ro',
                          '-v', f'{ROOT}/Simulation/logs/generated-worlds:/scenario:ro', '-v', f'{output}:/results']))
    if not args.plan_only:
        commands.append(('bridge', 'maritime-sim-evaluation:jazzy', ['python3', '/navigation_bridge.py'],
                         ['-e', 'ADAPTER_ENVIRONMENT=simulation', '-e', 'SIMULATION_NAVIGATION=1',
                          '-e', f'NAVIGATION_MISSION_TIMEOUT_S={args.mission_timeout}',
                          '-v', f'{ROOT}/Simulation/scripts/navigation_bridge.py:/navigation_bridge.py:ro']))
    processes, logs = {}, []
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    result = 0
    try:
        for name, image, command, options in commands:
            log = (output/(name+'.log')).open('w')
            logs.append(log)
            processes[name] = subprocess.Popen(common+['--name', 'maritime-nav-'+name]+options+[image]+command,
                                                stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+args.mission_timeout+210
        while time.monotonic() < deadline:
            completed = session_exit(processes, args.evaluate)
            if completed is not None:
                result = completed
                break
            time.sleep(.2)
        else:
            raise RuntimeError('Navigation session exceeded mission and startup time budget')
    except KeyboardInterrupt:
        result = 130
    finally:
        for name in ['bridge', 'judge', 'navigator', 'mapping', 'clock']:
            if name in processes:
                subprocess.run(['docker', 'stop', '-t', '20', 'maritime-nav-'+name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                processes[name].wait(timeout=25)
        for log in logs:
            log.close()
    raise SystemExit(result)


if __name__ == '__main__':
    main()

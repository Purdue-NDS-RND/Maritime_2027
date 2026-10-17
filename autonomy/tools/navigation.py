#!/usr/bin/env python3
"""Run an explicit camera navigation session against an existing simulator."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'run', 'test'])
    parser.add_argument('--task', choices=['gate', 'slalom'], default='slalom')
    parser.add_argument('--evaluate', action='store_true')
    args = parser.parse_args()
    if args.action == 'build':
        subprocess.run(['docker', 'build', '-t', 'maritime-autonomy:jazzy', '-f',
                        str(ROOT/'autonomy/container/Dockerfile'), str(ROOT/'autonomy')], check=True)
        subprocess.run(['docker', 'build', '-t', 'maritime-sim-evaluation:jazzy', '-f',
                        str(ROOT/'Simulation/tests/evaluation/container/Dockerfile'),
                        str(ROOT/'Simulation/tests/evaluation')], check=True)
        return
    if args.action == 'test':
        subprocess.run(['python3', '-m', 'unittest', 'discover', '-s', str(ROOT/'autonomy/tests'), '-v'], check=True)
        subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                        '-v', f'{ROOT}/autonomy/tests:/tests:ro', 'maritime-autonomy:jazzy',
                        'bash', '-lc', 'source /etc/maritime_autonomy_setup.bash && '
                        'python3 -m unittest discover -s /tests -p test_navigation_vision.py -v'], check=True)
        subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                        '-v', f'{ROOT}/Simulation/scripts:/navigation-scripts:ro',
                        '-v', f'{ROOT}/Simulation/tests/evaluation:/tests:ro',
                        'maritime-sim-evaluation:jazzy', 'python3', '-m', 'unittest', 'discover',
                        '-s', '/tests', '-p', 'test_navigation_bridge.py', '-v'], check=True)
        return
    for name in ['ardupilot-blueboat-sim', 'maritime-sim-adapter']:
        health = subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Health.Status}}', name], text=True).strip()
        if health != 'healthy':
            parser.error(f'{name} is {health}; start SCENARIO={args.task} BOAT_MODEL=dual make run')
    for suffix in ['navigator', 'bridge', 'judge']:
        if subprocess.run(['docker', 'inspect', 'maritime-nav-'+suffix],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            parser.error('An existing navigation session is present; stop it before starting another')
    output = ROOT/'Simulation/logs'/('navigation-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    print(f'Navigation logs: {output}', flush=True)
    common = ['docker', 'run', '--rm', '--init', '--network', 'host',
              '-e', 'ROS_DOMAIN_ID='+os.environ.get('ROS_DOMAIN_ID', '0'),
              '-e', 'FASTRTPS_DEFAULT_PROFILES_FILE=/etc/navigation-fastdds.xml',
              '-v', f'{ROOT}/Monitor/config/fastdds.xml:/etc/navigation-fastdds.xml:ro']
    commands = [('navigator', 'maritime-autonomy:jazzy', [
        'bash', '-lc', 'source /etc/maritime_autonomy_setup.bash && exec ros2 run maritime_navigation navigator '
        '--ros-args -r vessel/odometry:=/mavros/local_position/odom -p slalom_turns:='+('0' if args.task == 'gate' else '4')], [])]
    if args.evaluate:
        commands.append(('judge', 'maritime-sim-evaluation:jazzy', ['python3', '/navigation_evaluate.py'],
                         ['-v', f'{ROOT}/Simulation/tests/evaluation/navigation_evaluate.py:/navigation_evaluate.py:ro',
                          '-v', f'{ROOT}/Simulation/logs/generated-worlds:/scenario:ro', '-v', f'{output}:/results']))
    commands.append(('bridge', 'maritime-sim-evaluation:jazzy', ['python3', '/navigation_bridge.py'],
                     ['-e', 'ADAPTER_ENVIRONMENT=simulation', '-e', 'SIMULATION_NAVIGATION=1',
                      '-v', f'{ROOT}/Simulation/scripts/navigation_bridge.py:/navigation_bridge.py:ro']))
    processes = {}
    logs = []
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for name, image, command, options in commands:
            log = (output/(name+'.log')).open('w')
            logs.append(log)
            processes[name] = subprocess.Popen(common+['--name', 'maritime-nav-'+name]+options+[image]+command,
                                                stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+360
        while time.monotonic() < deadline:
            if processes['bridge'].poll() is not None:
                code = processes['bridge'].returncode
                if args.evaluate:
                    judge_code = processes['judge'].wait(timeout=15)
                    code = code or judge_code
                raise SystemExit(code)
            if processes['navigator'].poll() is not None:
                raise RuntimeError('Navigator exited; bridge deadman stops the boat')
            time.sleep(.5)
        raise RuntimeError('Navigation session exceeded 360 seconds')
    except KeyboardInterrupt:
        pass
    finally:
        # Stop the bridge first so its HOLD/disarm cleanup runs while ROS lives.
        for name in ['bridge', 'judge', 'navigator']:
            if name in processes:
                subprocess.run(['docker', 'stop', '-t', '25', 'maritime-nav-'+name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                processes[name].wait(timeout=30)
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()

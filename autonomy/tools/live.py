#!/usr/bin/env python3
"""Disposable live pipeline/viewer containers, independent of simulator bringup."""
import argparse
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
IMAGE = os.environ.get('MAPPING_IMAGE', 'maritime-mapping-view:jazzy')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'run', 'view', 'test'))
    args = parser.parse_args()
    if args.action == 'build':
        subprocess.run(['docker', 'build', '-t', 'maritime-autonomy:jazzy', '-f',
                        str(ROOT/'autonomy/container/Dockerfile'), str(ROOT/'autonomy')], check=True)
        subprocess.run(['docker', 'build', '-t', IMAGE, '-f',
                        str(ROOT/'Monitor/container/Dockerfile.mapping'), str(ROOT/'Monitor')], check=True)
        return
    domain = int(os.environ.get('ROS_DOMAIN_ID', '0'))
    view = os.environ.get('VIEW', 'plot')
    clock = os.environ.get('POSE_CLOCK', 'receipt')
    offset = float(os.environ.get('POSE_TIME_OFFSET_S', '0'))
    if not 0 <= domain <= 232 or view not in ('plot', 'none') or clock not in ('receipt', 'source'):
        parser.error('Use domain 0..232, VIEW=plot|none and POSE_CLOCK=receipt|source')
    if not math.isfinite(offset) or (clock == 'receipt' and offset != 0):
        parser.error('A finite manual offset requires POSE_CLOCK=source')
    gui = args.action in ('run', 'view') and view == 'plot'
    command = ['docker', 'run', '--rm', '--init', '--user', f'{os.getuid()}:{os.getgid()}',
               '--network', 'none' if args.action == 'test' else 'host',
               '-e', f'ROS_DOMAIN_ID={96 if args.action == "test" else domain}',
               '-e', 'PYTHONDONTWRITEBYTECODE=1',
               '-e', 'FASTRTPS_DEFAULT_PROFILES_FILE=/etc/live-fastdds.xml',
               '-v', f'{ROOT}/Monitor/tools:/opt/live:ro',
               '-v', f'{ROOT}/Monitor/config/fastdds.xml:/etc/live-fastdds.xml:ro',
               '-v', f'{ROOT}/Monitor/tests:/opt/live-tests:ro']
    if args.action == 'run':
        command += ['--name', f'maritime-rgb-mapping-{domain}']
    if args.action == 'test':
        results = ROOT/'Simulation/logs/live-mapping-validation'
        results.mkdir(parents=True, exist_ok=True)
        command += ['-v', f'{results}:/results', '-e', 'LIVE_MAPPING_SNAPSHOT=/results/live-mapping.png']
    for package in ('maritime_perception', 'maritime_localization'):
        command += ['-v', f'{ROOT}/autonomy/ros_ws/src/{package}:/opt/autonomy_ws/src/{package}:ro']
    with tempfile.TemporaryDirectory(prefix='maritime-mapping-') as temporary:
        if gui:
            display = os.environ.get('DISPLAY', '')
            if not display:
                parser.error('Popup requires DISPLAY; use VIEW=none for headless operation')
            if display.startswith(':'):
                socket = Path('/tmp/.X11-unix')/('X'+display[1:].split('.')[0])
                if not socket.exists():
                    parser.error(f'DISPLAY={display} has no X11 socket; use the active desktop DISPLAY '
                                 'and XAUTHORITY, or VIEW=none')
            cookie = subprocess.check_output(['xauth', 'nlist', display], text=True)
            if not cookie.strip():
                parser.error('No X11 cookie for DISPLAY; check XAUTHORITY or use VIEW=none')
            authority = Path(temporary)/'xauth'
            authority.touch(mode=0o600)
            subprocess.run(['xauth', '-f', str(authority), 'nmerge', '-'],
                           input='\n'.join('ffff'+line[4:] for line in cookie.splitlines())+'\n',
                           text=True, check=True)
            command += ['-e', f'DISPLAY={display}', '-e', 'XAUTHORITY=/tmp/live.xauth',
                        '-v', f'{authority}:/tmp/live.xauth:ro',
                        '-v', '/tmp/.X11-unix:/tmp/.X11-unix:ro']
        command += [IMAGE, args.action, '--clock', clock, '--pose-topic',
                    os.environ.get('POSE_TOPIC', '/mavros/local_position/odom'),
                    '--offset', str(offset)]
        if not gui:
            command.append('--no-window')
        # Docker forwards SIGINT; keep this process alive for its cleanup.
        previous = signal.signal(signal.SIGINT, lambda *_: None)
        try:
            raise SystemExit(subprocess.call(command))
        finally:
            signal.signal(signal.SIGINT, previous)


if __name__ == '__main__':
    main()

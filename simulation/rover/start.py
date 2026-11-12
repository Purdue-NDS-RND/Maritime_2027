"""Own three process groups; fresh state, no global process killing."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

children = []
logs = []


def launch(name, command, **kwargs):
    log = open(f'/sim/{name}.log', 'w')
    logs.append(log)
    child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True, **kwargs)
    children.append(child)


def stop(signum, frame):
    raise SystemExit(128 + signum)


def check_ports():
    sockets = []
    try:
        for kind, ports in ((socket.SOCK_DGRAM, (9002, 5501, 14559)),
                            (socket.SOCK_STREAM, (5760, 5762, 5763))):
            for port in ports:
                sock = socket.socket(socket.AF_INET, kind)
                sockets.append(sock)
                if kind == socket.SOCK_STREAM:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('0.0.0.0', port))
    finally:
        for sock in sockets:
            sock.close()


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    check_ports()
    state = Path('/sim/state')
    state.mkdir(exist_ok=False)
    os.environ['HOME'] = str(state)
    os.environ['XDG_RUNTIME_DIR'] = str(state / 'runtime')
    Path(os.environ['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
    gazebo = ['gz', 'sim', '-v4', '-r']
    if os.environ.get('ROVER_HEADLESS', '0') == '1':
        gazebo.append('-s')
    elif not os.environ.get('DISPLAY'):
        raise RuntimeError('visible Gazebo needs DISPLAY; use ROVER_HEADLESS=1 for automation')
    launch('gazebo', gazebo + ['/opt/rover/flat.sdf'])
    launch('sitl', ['/opt/ardupilot/build/sitl/bin/ardurover', '--model', 'JSON',
                    '--home', '51.566151,-4.034345,0,0', '--speedup', '1', '-w',
                    '--defaults', '/opt/ardupilot/Tools/autotest/default_params/rover.parm,/opt/ardupilot/Tools/autotest/default_params/rover-skid.parm,/opt/rover/rover.parm'], cwd=state)
    launch('mavproxy', ['mavproxy.py', '--master=tcp:127.0.0.1:5760',
                       '--out=udp:127.0.0.1:14550', '--out=udp:127.0.0.1:14551',
                       '--out=udp:127.0.0.1:14559', '--non-interactive',
                       '--streamrate=10', '--logfile=/sim/mavlink.tlog'], cwd=state)
    deadline = time.monotonic() + 120
    while True:
        for child in children:
            if child.poll() is not None:
                raise RuntimeError(f'process {child.args[0]} exited: {child.returncode}')
        if not Path('/sim/ready.json').exists() and time.monotonic() > deadline:
            raise RuntimeError('readiness deadline exceeded; see health and process logs')
        time.sleep(0.5)


if __name__ == '__main__':
    try:
        main()
    finally:
        for child in reversed(children):
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and any(c.poll() is None for c in children):
            time.sleep(0.1)
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        for log in logs:
            log.close()

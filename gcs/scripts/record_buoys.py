#!/usr/bin/env python3
"""Record GPS buoy points using a selected red, green or unknown mode."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import math
import os
import re
from pathlib import Path
import sys
import tempfile
import termios
import time
import tty
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


MAX_AGE_S = 3
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / 'recordings'
COLOR_KEYS = {'r': 'red', 'g': 'green', 'u': 'unknown'}


def new_output(directory=DEFAULT_DIRECTORY):
    """Reserve a fresh numbered map without overwriting another session."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    numbers = [int(match.group(1)) for path in directory.iterdir()
               if (match := re.fullmatch(r'buoy_(\d+)\.json', path.name))]
    index = max(numbers, default=0) + 1
    while True:
        path = directory / f'buoy_{index}.json'
        try:
            with path.open('x') as stream:
                stream.write('{"points": []}\n')
            return path
        except FileExistsError:
            index += 1


def number(value, low, high, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f'{name} must be a finite number in {low}..{high}')
    return value


def coordinates(value):
    if not isinstance(value, dict):
        raise ValueError('GPS position is missing')
    return {
        # Match the geographic range supported by the GCS point importer.
        'latitude': number(value.get('latitude'), -85, 85, 'latitude'),
        'longitude': number(value.get('longitude'), -180, 180, 'longitude'),
    }


def capture_position(snapshot, elapsed_s=0):
    """Reject missing, stale or invalid fixes, including time spent fetching."""
    if (not isinstance(snapshot, dict) or snapshot.get('source') != 'mavlink'
            or snapshot.get('stale') is not False
            or snapshot.get('connection_state') != 'live' or snapshot.get('error')):
        raise ValueError('Telemetry is unavailable or stale; check GCS Connections')
    for name in ('heartbeat_age_s', 'position_age_s', 'gps_age_s'):
        age = number(snapshot.get(name), 0, MAX_AGE_S, name)
        if age + elapsed_s > MAX_AGE_S:
            raise ValueError(f'{name} is too old after the HTTP request')
    fix = snapshot.get('gps_fix')
    if type(fix) is not int or not 3 <= fix <= 8:
        raise ValueError('A fresh 3D GPS fix or better is required')
    return coordinates(snapshot.get('position'))


def fetch_position(gcs_url):
    started = time.monotonic()
    request = Request(gcs_url.rstrip('/') + '/api/telemetry',
                      headers={'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=1) as response:
        snapshot = json.load(response)
    return capture_position(snapshot, time.monotonic() - started), snapshot


class PointFile:
    """Atomic simple-map edits; undo only points added during this invocation."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.original = self.read()
        self.document = json.loads(self.original) if self.original is not None else {'points': []}
        if isinstance(self.document, dict) and 'schema_version' in self.document:
            raise ValueError('Use a simple points JSON, not a native map or saved course file')
        self.points = self.document.get('points') if isinstance(self.document, dict) else self.document
        if not isinstance(self.points, list):
            raise ValueError('Output must contain a JSON point list or {"points": [...]}')
        names = set()
        for index, point in enumerate(self.points, 1):
            coordinates(point)
            name = str(point.get('id') or f'point_{index}')
            if not name or len(name) > 80 or name in names:
                raise ValueError('Existing points have invalid or duplicate IDs')
            names.add(name)
        self.initial_count = len(self.points)

    def read(self):
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def save(self, points):
        if self.read() != self.original:
            raise ValueError('Output changed outside this helper; quit and reopen it before recording')
        document = deepcopy(self.document)
        if isinstance(document, dict):
            document['points'] = points
        else:
            document = points
        payload = (json.dumps(document, indent=2, allow_nan=False) + '\n').encode()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.' + self.path.name,
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.original = payload
        self.document = document
        self.points = points

    def append(self, position, color='unknown'):
        if color not in COLOR_KEYS.values():
            raise ValueError('Select red, green or unknown')
        point = coordinates(position)
        if color != 'unknown':
            point.update(color=color, object_type='buoy')
        # Explicit imported IDs must not collide with the importer's generated IDs.
        names = {str(p.get('id') or f'point_{i}') for i, p in enumerate(self.points, 1)}
        if f'point_{len(self.points) + 1}' in names:
            index = 1
            while f'capture_{index}' in names:
                index += 1
            point['id'] = f'capture_{index}'
        self.save([*self.points, point])

    def undo(self):
        if len(self.points) <= self.initial_count:
            raise ValueError('No captures from this session to undo; existing points are preserved')
        self.save(self.points[:-1])


@contextmanager
def output_lock(path):
    """Keep a stable sidecar lock while the JSON inode is atomically replaced."""
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another recorder is using this output file') from error
        yield


@contextmanager
def keyboard():
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield fd
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def run(args):
    if args.output is None:
        args.output = new_output()
    with output_lock(args.output):
        output = PointFile(args.output)
        print(f'Output: {output.path} ({len(output.points)} existing points)')
        print(f'GPS source: {args.gcs_url}/api/telemetry (GCS Connections selects the vehicle)')
        print('r red | g green | u unknown | SPACE save | Backspace undo | q quit | Ctrl-C quit')
        print('Select r, g or u before capturing. Selection stays active until changed.')
        color = None
        print('Place the GPS antenna at the intended map position; alongside is an offset.')
        last_space = -math.inf
        with keyboard() as fd:
            print('Ready; each Space requests fresh GPS.', flush=True)
            while True:
                key = os.read(fd, 1).decode(errors='replace').lower()
                if not key or key == 'q':
                    break
                if key in COLOR_KEYS:
                    color = COLOR_KEYS[key]
                    print(f'Mode: {color}', flush=True)
                elif key in ('\x7f', '\x08'):
                    try:
                        output.undo()
                        print(f'Undid last capture. {len(output.points)} points saved.', flush=True)
                    except (ValueError, OSError) as error:
                        print(f'Undo refused: {error}', flush=True)
                elif key == ' ':
                    if color is None:
                        print('Select r, g or u before pressing Space.', flush=True)
                        continue
                    now = time.monotonic()
                    # Ignore key repeat. Flush queued keys after the bounded request
                    # so a held Space cannot capture a backlog of unwanted points.
                    if now - last_space < 0.75:
                        last_space = now
                        continue
                    last_space = now
                    try:
                        position, snapshot = fetch_position(args.gcs_url)
                        output.append(position, color)
                        message = (f'Saved #{len(output.points)} {color}: '
                                   f'{position["latitude"]:.8f}, {position["longitude"]:.8f} '
                                   f'(GPS fix {snapshot["gps_fix"]}, '
                                   f'vehicle {snapshot.get("system_id")}/{snapshot.get("component_id")})')
                    except (ValueError, OSError, URLError) as error:
                        message = f'Capture refused; no point saved: {error}'
                    finally:
                        termios.tcflush(fd, termios.TCIFLUSH)
                        last_space = time.monotonic()
                    print(message, flush=True)
        print(f'Finished. {len(output.points)} points in {output.path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=None,
                        help='New or existing simple GPS points JSON; saved after each capture '
                             '(default: next gcs/recordings/buoy_N.json in this checkout)')
    parser.add_argument('--gcs-url', default='http://127.0.0.1:8080',
                        help='Running GCS origin (default: http://127.0.0.1:8080)')
    args = parser.parse_args()
    origin = urlsplit(args.gcs_url)
    if (origin.scheme not in ('http', 'https') or not origin.hostname
            or origin.username is not None or origin.password is not None
            or origin.path not in ('', '/') or origin.query or origin.fragment):
        parser.error('--gcs-url must be an HTTP(S) origin without credentials, path or query')
    args.gcs_url = args.gcs_url.rstrip('/')
    if not sys.stdin.isatty():
        parser.error('Run in an interactive terminal so Space can capture without Enter')
    try:
        run(args)
    except KeyboardInterrupt:
        print('\nStopped; completed captures remain saved.')
    except (ValueError, OSError) as error:
        parser.exit(1, f'Recorder stopped: {error}\n')


if __name__ == '__main__':
    main()

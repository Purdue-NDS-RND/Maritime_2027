"""List USB serial devices and resolve an unambiguous controller at launch.

This runs on the host using only Python's standard library. Discovery never
opens a serial port or sends MAVLink; the application confirms vehicle identity.
"""

import json
from pathlib import Path
import re
import stat
import sys


CONTROLLERS = re.compile(r"cube|pixhawk|pixracer|holybro|px4|cuav|ardupilot|autopilot", re.I)


def discover(root=Path('/dev')):
    devices = {}
    aliases = sorted((root / 'serial/by-id').glob('*'))
    # Prefer a stable alias over its numbered tty, and the primary USB interface.
    for path in aliases + sorted(root.glob('ttyACM*')) + sorted(root.glob('ttyUSB*')):
        try:
            if not stat.S_ISCHR(path.stat().st_mode):
                continue
            target = path.resolve()
        except OSError:
            continue
        if target in devices:
            continue
        primary = not re.search(r'-if(?!00)[0-9a-f]{2}(?:-|$)', path.name, re.I)
        devices[target] = {'path': str(path), 'target': str(target),
                           'recognized': bool(CONTROLLERS.search(path.name)) and primary}
    return list(devices.values())


def listing(devices):
    return '\n'.join(f"  {d['path']} -> {d['target']}"
                     f" {'[controller candidate]' if d['recognized'] else '[other serial interface]'}"
                     for d in devices) or '  No USB serial devices found.'


def resolve(config, root=Path('/dev')):
    boat = config.get('services', {}).get('boat', {})
    device = next((d['source'] for d in boat.get('devices', [])
                   if d['target'] == '/dev/boat-fcu'), None)
    if device is None:
        return None
    if device == 'auto':
        devices = discover(root)
        candidates = [d for d in devices if d['recognized']]
        if len(candidates) != 1:
            reason = 'No recognized flight controller' if not candidates else 'Multiple flight controllers'
            raise ValueError(f"{reason} found.\n{listing(devices)}\n"
                             'Set BOAT_SERIAL_DEVICE to the intended device path in field.env; '
                             'make scan lists devices. No serial ports were opened.')
        device = candidates[0]['path']
    path = Path(device)
    try:
        info = path.stat()
    except OSError as error:
        raise ValueError(f"Cannot access flight controller {path}: {error}. "
                         'Run make scan, then update field.env or use BOAT_SERIAL_DEVICE=auto.') from error
    if not stat.S_ISCHR(info.st_mode):
        raise ValueError(f'{path} is not a character device; choose a serial device with make scan.')
    groups = boat.get('group_add', [])
    if not groups:
        raise ValueError('Set BOAT_SERIAL_GID=auto or the numeric serial device group in field.env.')
    group = str(info.st_gid) if str(groups[0]) == 'auto' else str(groups[0])
    if not group.isdecimal():
        raise ValueError('BOAT_SERIAL_GID must be auto or a numeric group ID.')
    if '\n' in str(path) or '\r' in str(path):
        raise ValueError('Serial paths containing line breaks are not supported.')
    print(f'[boat] Selected USB/serial device: {path} -> {path.resolve()} (group {group}).', file=sys.stderr)
    if group != str(info.st_gid):
        print(f'[boat] Warning: configured group {group} differs from device group {info.st_gid}.', file=sys.stderr)
    return str(path), group


def main():
    if sys.argv[1:] == ['scan']:
        print('USB serial devices (name matches are candidates, not verified MAVLink identities):')
        print(listing(discover()))
        print('Use BOAT_SERIAL_DEVICE=auto for one recognized controller, or select a listed path in field.env.')
        return
    if sys.argv[1:] != ['resolve']:
        raise ValueError('Choose scan or resolve')
    result = resolve(json.load(sys.stdin))
    if result:
        print('\n'.join(result))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(f'[boat] {error}', file=sys.stderr)
        sys.exit(1)

"""Explicit simulator tuning setup/rollback with the boat service stopped.

Run from the boat image with simulator scripts and logs mounted. This helper
owns UDP 14551 exclusively and never runs during normal boat/GCS operation.
"""
import argparse
import json
from pathlib import Path
import time

from pymavlink import mavutil
from boat_app.executor import Executor
from calibrate import ALLOWED, set_parameter
from measured_profiles import request_position_rate, verify_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore'))
    parser.add_argument('profile', type=Path)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--baseline-position-hz', type=int, choices=(4, 10, 20))
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    state = {'profile': profile, 'events': []}

    def save():
        temporary = args.state.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(args.state)

    def emit(event):
        state['events'].append({'monotonic_s': time.monotonic(), **event})

    link = mavutil.mavlink_connection('udpin:127.0.0.1:14551', source_system=246, source_component=192)
    controller = Executor(link, emit)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            controller.tick()
            try:
                controller.fresh()
                break
            except Exception:
                time.sleep(.1)
        controller.fresh()
        if controller.armed or controller.speed > .2:
            raise RuntimeError('settings require a disarmed stationary vehicle')
        if args.action == 'apply':
            if args.state.exists():
                raise RuntimeError('state already exists; do not overwrite rollback evidence')
            if (args.state.parent / 'RESTORATION_FAILED.json').exists():
                raise RuntimeError('prior restoration failure requires resolution')
            if args.baseline_position_hz is None:
                raise RuntimeError('explicit launcher telemetry baseline required')
            values = profile['parameters']
            for name, value in values.items():
                if name not in ALLOWED or not ALLOWED[name][0] <= value <= ALLOWED[name][1]:
                    raise RuntimeError('unsupported setting ' + name)
            state.update(status='preparing', original={name: controller.parameter(name) for name in values},
                         launcher_position_rate_hz=args.baseline_position_hz)
            save()
            try:
                for name, value in values.items():
                    set_parameter(controller, name, value)
                verify_profile(controller, profile['id'], args.profile.parent, profile['geometry_sha256'])
                state.update(status='applied', applied={name: controller.parameter(name) for name in values})
                save()
            except BaseException:
                restore(controller, state, args.state, save)
                raise
        else:
            state = json.loads(args.state.read_text())
            if state['profile'] != profile:
                raise RuntimeError('profile differs from saved restoration state')
            restore(controller, state, args.state, save)
        print(state['status'])
    finally:
        link.close()


def restore(controller, state, state_path, save):
    failures = {}
    state['restored'] = {}
    for name, value in state['original'].items():
        try:
            set_parameter(controller, name, value)
            state['restored'][name] = controller.parameter(name)
        except Exception as error:
            failures[name] = str(error)
    try:
        request_position_rate(controller, state['launcher_position_rate_hz'])
    except Exception as error:
        failures['position_rate'] = str(error)
    state.update(status='restore_failed' if failures else 'restored', errors=failures)
    save()
    if failures:
        (state_path.parent / 'RESTORATION_FAILED.json').write_text(json.dumps(state, indent=2) + '\n')
        raise RuntimeError(str(failures))


if __name__ == '__main__':
    main()

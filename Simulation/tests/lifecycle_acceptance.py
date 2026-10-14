#!/usr/bin/env python3
"""Explicit local simulation lifecycle acceptance; never run against hardware.

Run from Simulation/: python3 tests/lifecycle_acceptance.py. Logs and a JSON
result go under logs/lifecycle-<UTC>. Only LOG_DISARMED is changed for the
parameter test; the original stopped SITL EEPROM is restored on every exit.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
CONTAINERS = ("ardupilot-blueboat-sim", "maritime-sim-adapter", "maritime-autonomy")


def command(*args, check=True, timeout=60):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True,
                          check=check, timeout=timeout)


def assert_clean():
    remaining = command("docker", "ps", "-a", "--format", "{{.Names}}").stdout.splitlines()
    assert not set(CONTAINERS) & set(remaining), remaining
    assert not (ROOT / "logs/active-xauth.path").exists(), "active Xauthority record remains"
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    assert not list(runtime.glob("ardupilot-blueboat-xauth.*")), "temporary Xauthority remains"
    sockets = command("ss", "-H", "-lun").stdout
    for line in sockets.splitlines():
        local_port = line.split()[3].rsplit(":", 1)[-1]
        assert local_port not in {"14550", "14551", "14552", "14559", "9002"}, line


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=75)
        except subprocess.TimeoutExpired:
            command("./scripts/run.sh", "--down", timeout=75)
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            raise AssertionError("launcher exceeded its shutdown deadline")
    assert_clean()


def launch(output, name, overrides=None):
    environment = {**os.environ, "SCENARIO": "one"}
    for key in ("WORLD", "BUOY_SEED", "WIPE_PARAMS", "CAMERA_ENABLED"):
        environment.pop(key, None)
    environment.update(overrides or {})
    log = (output / f"{name}.log").open("w")
    process = subprocess.Popen(["./scripts/run.sh"], cwd=ROOT, env=environment,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    log.close()
    return process


def ready(process, timeout=220):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert process.poll() is None, f"startup exited {process.returncode}"
        healthy = []
        for name in CONTAINERS:
            result = command("docker", "inspect", "-f", "{{.State.Health.Status}}", name,
                             check=False)
            healthy.append(result.returncode == 0 and result.stdout.strip() == "healthy")
        if all(healthy):
            time.sleep(3)
            assert process.poll() is None
            environment = json.loads(command("docker", "inspect", "-f", "{{json .Config.Env}}", CONTAINERS[0]).stdout)
            environment = dict(item.split("=", 1) for item in environment)
            directory = ROOT / "logs/runs" / environment["RUN_ID"]
            recorded = (directory / "identity.txt").read_text()
            fingerprint = hashlib.sha256((directory / "compose.yaml").read_bytes()).hexdigest()
            assert environment["RUN_CONFIG_SHA256"] == fingerprint
            assert f"configuration_sha256={fingerprint}" in recorded
            assert "application_state=empty_simulation_placeholder" in recorded
            manifest = json.loads((directory / "scenario.manifest.json").read_text())
            assert manifest["scenario"] == "one" and len(manifest["buoys"]) == 1
            return {"run_id": environment["RUN_ID"], "configuration_sha256": fingerprint,
                    "identity": recorded}
        time.sleep(2)
    raise AssertionError("stack did not become semantically ready")


def inject(container, executable, sig):
    script = """import os, pathlib, signal, sys
matches = []
for entry in pathlib.Path('/proc').iterdir():
    if not entry.name.isdigit() or int(entry.name) == os.getpid(): continue
    try: argv = (entry / 'cmdline').read_bytes().split(b'\\0')
    except (FileNotFoundError, PermissionError, ProcessLookupError): continue
    if argv and pathlib.PurePath(argv[0].decode()).name == sys.argv[1]:
        matches.append(int(entry.name))
assert len(matches) == 1, matches
os.kill(matches[0], int(sys.argv[2]))
print('injected', sys.argv[1], matches[0], sys.argv[2])
"""
    return command("docker", "exec", container, "python3", "-c", script,
                   executable, str(sig)).stdout.strip()


def parameter(expected=None, value=None):
    script = """import sys, time
from pymavlink import mavutil
m = mavutil.mavlink_connection('udp:127.0.0.1:14551', source_system=255)
assert m.wait_heartbeat(timeout=20), 'heartbeat timeout'
name = b'LOG_DISARMED'
deadline = time.monotonic() + 15
value = None if sys.argv[1] == 'read' else float(sys.argv[1])
while time.monotonic() < deadline:
    if value is None: m.mav.param_request_read_send(1, 1, name, -1)
    else: m.mav.param_set_send(1, 1, name, value, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
    if msg and msg.param_id == 'LOG_DISARMED' and (value is None or msg.param_value == value):
        print(msg.param_value)
        break
else: raise AssertionError('parameter acknowledgment timeout')
"""
    result = float(command("docker", "exec", CONTAINERS[0], "python3", "-c", script,
                           "read" if value is None else str(value)).stdout.strip())
    if expected is not None:
        assert result == expected, (result, expected)
    return result


def run_case(output, name):
    overrides = {}
    if name == "gazebo_startup":
        overrides = {"SCENARIO": "", "ROS_SIM": "1", "WORLD": "blueboat_waves.sdf",
                     "CAMERA_ENABLED": "1", "GAZEBO_STARTUP_TIMEOUT": "12",
                     "STACK_STARTUP_TIMEOUT": "35"}
    if name == "adapter_startup":
        overrides = {"SCENARIO": "", "ROS_SIM": "1", "WORLD": "blueboat_waves.sdf",
                     "CAMERA_ENABLED": "0", "MAVLINK_MAVROS": "udp:127.0.0.1:14559",
                     "STACK_STARTUP_TIMEOUT": "65"}
    process = launch(output, name, overrides)
    try:
        if name in ("gazebo_startup", "adapter_startup"):
            code = process.wait(timeout=160)
            assert code != 0, "failed startup was reported successful"
            assert_clean()
            text = (output / f"{name}.log").read_text()
            category = "gazebo_vehicle_sitl" if name == "gazebo_startup" else "camera_calibration_tf_fcu"
            assert "ERROR:" in text and category in text, text[-1500:]
            assert "Stack startup passed" not in text
            return {"exit": code, "bounded_failed_startup": True}
        identity = ready(process)
        if name == "double_start":
            for filename in ("ros_boundary_smoke.py", "boundary_contract.py"):
                command("docker", "cp", str(ROOT.parent / "tests" / filename),
                        f"{CONTAINERS[2]}:/tmp/{filename}")
            boundary = command("docker", "exec", CONTAINERS[2], "bash", "-lc",
                               "source /etc/maritime_autonomy_setup.bash && python3 /tmp/ros_boundary_smoke.py --autonomy")
            (output / "autonomy-boundary.log").write_text(boundary.stdout + boundary.stderr)
            assert "BOUNDARY PASS:" in boundary.stdout
            before = command("docker", "inspect", "-f", "{{.Id}}", *CONTAINERS).stdout
            authority = (ROOT / "logs/active-xauth.path").read_text()
            second = command("./scripts/run.sh", check=False, timeout=15)
            assert second.returncode != 0 and "ERROR:" in second.stderr
            assert process.poll() is None
            assert command("docker", "inspect", "-f", "{{.Id}}", *CONTAINERS).stdout == before
            assert (ROOT / "logs/active-xauth.path").read_text() == authority
            stop(process)
            return {"second_launch_exit": second.returncode, "active_stack_preserved": True,
                    "autonomy_boundary_probe": "PASS", **identity}
        if name in ("signal_int", "signal_term"):
            sig = signal.SIGINT if name == "signal_int" else signal.SIGTERM
            process.send_signal(sig)
            code = process.wait(timeout=75)
            assert code == 128 + sig, code
            assert_clean()
            return {"exit": code, **identity}
        if name in ("simulator_exit", "autonomy_exit"):
            target = CONTAINERS[0] if name == "simulator_exit" else CONTAINERS[2]
            # Stop just the selected required service. The launcher must notice
            # that exit, report failure, and tear down the remaining services.
            injected_at = time.monotonic()
            stopped = command("docker", "stop", "--timeout", "15", target).stdout.strip()
            assert stopped == target, stopped
            code = process.wait(timeout=75)
            assert code != 0, "required service exit was reported successful"
            assert_clean()
            text = (output / f"{name}.log").read_text()
            assert f"required service {target} failed" in text, text[-1500:]
            directory = ROOT / "logs/runs" / identity["run_id"]
            assert (directory / "failure.log").stat().st_size > 0
            return {"exit": code, "stopped_service": target,
                    "failure_cleanup_s": round(time.monotonic() - injected_at, 1), **identity}
        executable = "camera_boundary" if name in ("child_exit", "camera_silence") else "mavros_node"
        sig = signal.SIGTERM if name == "child_exit" else signal.SIGSTOP
        injection = inject(CONTAINERS[1], executable, sig)
        code = process.wait(timeout=220)
        assert code != 0
        assert_clean()
        text = (output / f"{name}.log").read_text()
        assert "required service" in text and "failed" in text
        return {"exit": code, "injection": injection, **identity}
    finally:
        stop(process)


def persistence(output):
    state = ROOT / "logs/state/eeprom.bin"
    backup = output / "original-eeprom.bin"
    existed = state.exists()
    if existed:
        shutil.copy2(state, backup)
    process = None
    identities = []
    try:
        process = launch(output, "parameters-initial", {"WIPE_PARAMS": "1"})
        identities.append(ready(process))
        baseline = parameter()
        changed = 1.0 if baseline == 0.0 else 0.0
        parameter(expected=changed, value=changed)
        time.sleep(3)
        stop(process)
        process = launch(output, "parameters-restart")
        identities.append(ready(process))
        parameter(expected=changed)
        stop(process)
        process = launch(output, "parameters-wipe", {"WIPE_PARAMS": "1"})
        identities.append(ready(process))
        parameter(expected=baseline)
        stop(process)
        assert len({item["run_id"] for item in identities}) == 3
        for item in identities:
            directory = ROOT / "logs/runs" / item["run_id"]
            assert (directory / "identity.txt").read_text() == item["identity"]
            assert hashlib.sha256((directory / "compose.yaml").read_bytes()).hexdigest() == item["configuration_sha256"]
            assert (directory / "services.log").stat().st_size > 0
        assert state.stat().st_size > 0
        return {"baseline": baseline, "retained_after_restart": changed,
                "reset_after_wipe": baseline, "original_eeprom_restored": existed,
                "runs": [item["run_id"] for item in identities], "logs_retained": True}
    finally:
        try:
            if process is not None:
                stop(process)
        finally:
            # Do not overwrite an active SITL EEPROM, but unrelated socket or
            # display-artifact failures must not prevent restoring user state.
            simulator = command("docker", "inspect", "-f", "{{.State.Running}}",
                                CONTAINERS[0], check=False)
            assert simulator.returncode != 0 or simulator.stdout.strip() == "false", "cannot restore EEPROM while SITL is running"
            if existed:
                shutil.copy2(backup, state)
            else:
                state.unlink(missing_ok=True)
            assert_clean()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="gazebo_startup,adapter_startup,simulator_exit,child_exit,autonomy_exit,camera_silence,fcu_silence,signal_int,signal_term,double_start,parameters")
    args = parser.parse_args()
    allowed = {"gazebo_startup", "adapter_startup", "simulator_exit", "child_exit", "autonomy_exit", "camera_silence",
               "fcu_silence", "signal_int", "signal_term", "double_start", "parameters"}
    if not set(args.cases.split(",")) <= allowed:
        parser.error("unknown lifecycle case")
    output = ROOT / "logs" / ("lifecycle-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True)
    assert_clean()
    results = []
    for name in args.cases.split(","):
        started = time.monotonic()
        print(f"Starting {name}; evidence {output}", flush=True)
        try:
            evidence = persistence(output) if name == "parameters" else run_case(output, name)
            results.append({"case": name, "status": "PASS", "elapsed_s": round(time.monotonic() - started, 1), **evidence})
        except Exception as error:
            results.append({"case": name, "status": "FAIL", "error": str(error)})
            (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
            raise
        print(json.dumps(results[-1]), flush=True)
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()

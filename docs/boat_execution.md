# Boat-only supplied-mission execution

The boat supports supplied GPS mission input, upload, explicit start, telemetry
progress and measured finish checks through local ROS services and loopback HTTP.
The GCS adds approval/clearance checks; simulator tools independently evaluate
passage. The local-file path remains independently testable.

## Interfaces and ownership

One ROS 2 node named `boat_mission` owns a direct `pymavlink` connection, using
source system 245/component 191. The first ArduPilot surface-boat heartbeat
selects its target system/component. Other sources cannot change its progress
or complete requests. The example uses the unchanged simulator port 14551.

Local `std_srvs/srv/Trigger` services are `/boat_mission/upload`, `start`, `stop`
and `disarm`. Successful upload means ArduPilot accepted the full transfer and
downloaded items match the supplied mission. Successful start means armed and
AUTO heartbeats were observed. Neither means navigation completed.
`/boat_mission/status` is `std_msgs/msg/String` JSON containing lifecycle state,
mission identity/hash, armed/mode, position, speed, GPS fix, telemetry ages,
current item and last reached item. It is a provisional local debug interface,
not an agreed vehicle-GCS format.

Service operations are serialized and bounded by timeouts. Status publication
and other services wait during upload/start/stop; MAVLink telemetry and companion
heartbeats continue. Independent Pixhawk/RC takeover remains essential and
unverified. A file lock prevents another boat process using the same evidence
directory; it does not exclude other MAVLink clients or log directories.

## Mission and execution

The local JSON file contains a mission identifier, GPS waypoints, speed, finish
radius/speed/settle interval, execution timeout, and maximum start-to-first-point
distance. A canonical SHA-256 identifies the normalized input. Snapshots are
saved before upload. Operator approval currently consists of explicit upload
and start calls on that file; GCS approval uses the HTTP interface below.

ArduPilot item zero is home and items one onward are supplied waypoints, at
zero relative altitude. Speed is a separately acknowledged start command,
applied in AUTO while still disarmed, before the arm command. A leading mission
speed item was observed to execute without applying its speed while AUTO was
initially loitering; placing it after the first waypoint applied it too late
for that leg. The start transaction therefore verifies speed acceptance before
allowing powered motion. Requested speed is a controller target, not a guarantee
that measured speed never overshoots.
ArduPilot handles turns and waypoint acceptance. Lines between waypoints do
not establish its executed path or hull clearance. No RTL or next task is added.

Upload requires fresh heartbeat, 3D GPS and position, a disarmed boat outside
AUTO, successful final `MISSION_ACK`, and matching mission readback. Duplicate
requests are supported; timeouts fail explicitly. A failed replacement
invalidates prior local start authorization. Start verifies stored items again
to detect post-upload changes. Concurrent mission/control producers are not
supported; there is no distributed command lock.

Start requires `MIS_DONE_BEHAVE` to be stop (0) or loiter (1), selects HOLD and
mission item one, enters AUTO disarmed, confirms speed acceptance, then arms
without force. The live parameter is
logged. The retained boat firmware reports loiter (1); a cached parameter list
initially reported zero, so cached lists are not authoritative. The app requests
HOLD at final waypoint arrival regardless of those two firmware end settings.
Parameters, simulator dynamics and source pins are retained. ACRO/manual end
settings are rejected.

The normal lifecycle is `ready -> uploading -> uploaded -> starting -> executing
-> stopping -> complete`. Faults report `failed`; mode changes/disarm report
`interrupted`; explicit stop/disarm reports `stopped`. A new upload/start is
required after interruption, completion or application restart.

On the final waypoint-reached report, the app requests HOLD and verifies GPS
position inside the finish radius and horizontal speed below the selected
threshold throughout the settle interval. It leaves the boat in HOLD awaiting
the operator. Disarm is explicit. This uses reported navigation telemetry,
not independent simulator truth or whole-hull passage. HOLD does not imply
station keeping after completion.

Heartbeat/position ages above three seconds, GPS age above five seconds or fix
below 3D, and execution/finish timeout cause failure. Best-effort HOLD is
attempted only when a fresh heartbeat still reports owned AUTO. Observed manual
mode is not overridden. Without telemetry, stop cannot be confirmed. Application
shutdown attempts the same cleanup; SIGKILL, power loss or network failure cannot
guarantee it. Firmware failsafe settings and physical RC acceptance remain open.
GCS/local status-client disconnection does not stop the mission. `ready` means
connected, not guaranteed ready to arm; ArduPilot retains its pre-arm checks.
The command client exits nonzero on a refused request or response timeout.

## Validation

See [boat instructions](../boat/README.md). Host checks cover mission parsing,
syntax and Compose resolution. Container tests cover rejected/corrupt uploads,
duplicate requests, other-source filtering, manual takeover, stale telemetry,
finish conditions, speed rejection before arming, multiple-waypoint ordering,
and actual ROS node construction/UDP heartbeat reception.

## Runtime evidence

Validated on 2026-10-27 local time (final evidence timestamps 2026-10-28 UTC),
on `revamp`, using calm open water with cameras disabled. The example input
`boat/examples/mission.json` was uploaded, downloaded and compared, then
explicitly started. Both command clients exited before arrival; no continuing
client commands were needed. These are measured GPS/velocity reports from
ArduPilot, not independent Gazebo trajectory or hull-clearance measurements.

| Setting or measurement | Result |
| --- | --- |
| Requested speed | 1.0 m/s, accepted before arming |
| Sampled peak horizontal speed | 1.20 m/s; target is not a strict speed cap |
| Reported start-to-finish displacement | 13.17 m |
| Reported error from finish waypoint | 1.23 m, within selected 3 m radius |
| Speed when completion was declared | 0.05 m/s, below selected 0.2 m/s |
| Finish settling interval | 5.19 s observed, 5 s required |
| Armed execution to completion | 21.22 s |
| End behavior | HOLD confirmed; explicit stop and disarm also confirmed |

All 16 container tests passed. Host validation and the retained simulator
`make validate` passed, including Gazebo SDF validation with Docker access.
There was no fresh full simulator source rebuild. The existing pinned simulator
image had an older startup script, so a separate temporary validation image
`maritime-milestone1-sim:validation` overlaid the current checkout's startup,
healthcheck, scripts, configuration and worlds while retaining simulator
binaries. The original `ardupilot-blueboat:4.7.0` tag was preserved. Its recipe
is saved under ignored `simulation/logs/boat-validation/Dockerfile.sim-validation`.
For reproducibility, use that recorded recipe or build the current simulator
normally before running the documented commands.

Final simulator run: `20261028T004806-298674`. Boat session:
`simulation/logs/boat/20261028T004745-1793148465698569842/`. The session contains
mission snapshots, event/progress JSONL, and `simulation-run.txt`. The summary
is `simulation/logs/boat-validation/final-runtime.json`; build/test/launch logs
are alongside it. Earlier diagnostic sessions remain preserved. One early
attempt was refused by the firmware's gyro consistency pre-arm check; no
checks were disabled and no force-arm was used.

This initial open-water run established supplied-mission execution only. Later
simulator slalom, clearance and fault results are recorded in
[Milestone 1](milestone1.md#recorded-simulator-results) and below. Physical RC,
radio networking, Jetson deployment and real-boat behavior remain unverified.

References: [MAVLink mission protocol](https://mavlink.io/en/services/mission.html)
and [ArduPilot Rover mission commands](https://ardupilot.org/rover/docs/common-mavlink-mission-command-messages-mav_cmd.html).
The exact retained firmware source was also inspected for AUTO startup, mission
speed and end behavior.

## Milestone 1 HTTP and command ownership

The boat also serves loopback HTTP on `127.0.0.1:8091` (ROS parameter
`http_port`). HTTP and the retained local-file ROS services submit to one
boat-owned queue. Only its worker receives/sends MAVLink, runs execution ticks,
or changes execution state; status readers consume snapshots. ROS uses
reentrant service callbacks so STOP can interrupt another pending service.

- `PUT /missions/{id}` accepts exactly `approval_id`, `revision_sha256`,
  and the existing `mission` object.
- `POST /missions/{id}/start` starts that verified current mission explicitly.
- `POST /stop`, `POST /disarm` retain the existing HOLD/disarm checks.
- `GET /operations/{id}` returns pending/running/succeeded/failed/unknown.
- `GET /status` returns the vehicle/mission snapshot, heading and telemetry ages.

Long commands return HTTP 202 and an operation ID. Receipt is distinct from
confirmed ArduPilot acceptance. Repeating identical upload/start identity
returns the recorded operation, including after process restart; a conflicting
ID/envelope is rejected. A restart marks unfinished operations unknown and
never restores start authorization or automatically resumes a mission. A failed
mission needs a new explicit revision/ID. Inspect status after ambiguous
outcomes rather than automatically retrying start with a new ID.

STOP raises cancellation checked inside MAVLink waits and before commands,
invalidates older queued commands and runs before ordinary work. Its confirmed
result is separate from receipt. Cancelled work cannot later proceed to arm.
Historical operations and mission envelopes are saved under the boat log
root in `operations.json`; mission/event evidence retains individual sessions.

Mission upload/start has no navigation-profile, geometry identity, tuning-gain
or telemetry-rate dependency. ArduPilot tuning and simulation calibration tools
belong to `simulation/`; the boat application neither applies nor verifies their
settings. Mission target speed is a finite positive value supplied by the GCS
or local mission file, with no application speed cap. Start still requires an
acknowledged speed command before arming. Firmware limits and actual tracking
remain ArduPilot's responsibility. Fresh telemetry, mission readback, finish
behavior checks, STOP, takeover and arming checks remain enforced.

Local file/ROS tests remain independent of the map/GCS and require no special
profile identifier. No buoy map/truth is sent in the boat mission. Old transfer
envelopes containing `navigation_profile_id` must be regenerated by explicitly
reviewing and approving the route in the updated GCS. Historical journals remain
available; no mission resumes automatically.

Historical verification passed 26 boat tests. Three consecutive browser-started full slaloms
passed the selected simulator acceptance at a commanded 2.0 m/s target. Measured
speeds, independent hull/finish checks, GCS-loss evidence and physical limits are in [Milestone 1 results](milestone1.md#recorded-simulator-results).

## Recorded control and telemetry fault checks

These used the existing boat image in run `20261028T023002-442841`, away from
course obstacles. A simulation-only relay bound the unchanged simulator API port
14551, with the boat temporarily configured to receive at 14651. No committed
port/default configuration changed. The separately supplied GPS missions used
the retained `local-file-unvalidated` boat-only path; these tests do not claim
GCS clearance approval or slalom passage.

- Dropping only GLOBAL_POSITION_INT while retaining heartbeat/GPS caused failure
  after position age exceeded 3 s. ArduPilot HOLD was confirmed with fresh
  heartbeat, and restoring position telemetry did not resume execution.
- Operator STOP during a live mission confirmed HOLD; explicit disarm succeeded
  after speed fell below 0.2 m/s.
- Dropping all telemetry caused a stale-heartbeat failure after 3 s. Without a
  fresh heartbeat, the app could not confirm stop. After link restoration,
  ArduPilot was still AUTO while the app remained failed; an explicit STOP then
  confirmed HOLD and disarm. This exposes the recovery-policy choice: deferred
  HOLD once fresh AUTO is observed versus requiring an operator STOP. No claim
  is made that total telemetry loss autonomously stops the vehicle.
- An independent client on the retained operator port 14550 selected MANUAL.
  The boat app reported interrupted, preserved MANUAL for the observation window,
  and required explicit new authorization. Subsequent explicit STOP/disarm
  succeeded. This verifies independent MAVLink takeover in simulation, not RC
  hardware or physical radio failsafes.

Scripts, receipts, per-case status samples and relay transitions are retained as
`fault_cases.py`, `fault_relay.py`, `manual_mode.py`, `fault-cases.jsonl`,
`fault-relay-events.jsonl` and `fault-cases-retry.log` under `simulation/logs/milestone1-followup/`.
The first harness launch preceded HTTP readiness and was refused before any
mission action; its error log is preserved separately. The retried harness
completed all four checks and left the boat disarmed in HOLD.

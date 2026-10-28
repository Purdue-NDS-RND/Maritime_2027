# Boat-only supplied-mission execution

This first implementation slice supports local GPS mission input, upload,
explicit start, telemetry progress and measured finish checks. GCS integration,
object-map export, clearance checks and independent passage evaluation remain
subsequent work.

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
and start calls on that file; future GCS approval is separate work.

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

Only the supplied-mission execution step is established here. Repeated slalom,
multi-leg runtime passage, contacts, stern clearance, physical RC takeover,
network faults, Jetson deployment and real-boat behavior remain unverified.
Next is resolved simulator object-map export with measured GPS-frame alignment.

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
  `navigation_profile_id`, and the existing `mission` object.
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

GCS profiles are read-only files under `/profiles`. The boat checks active
firmware version and source hash, configured geometry identity
(`BOAT_GEOMETRY_SHA256`) and readbacks of the five measured waypoint parameters
both at upload and at start. Profiles can also specify steering feedforward
`ATC_STR_RAT_FF` and speed P/I gains `ATC_SPEED_P` / `ATC_SPEED_I`; missing gains
require the original defaults 0.2 / 0.1 / 0.2 respectively. A measured profile
cannot authorize different live gains. The boat never silently changes them.
Selected position rates (4/10/20 Hz) are requested and checked against actual
source-timestamp frame spacing at both upload and start, not just command ACKs.
The simulator launcher must select the matching MAVProxy stream rate. Local
file/ROS tests retain the explicit `local-file-unvalidated` profile and remain
independent of the map/GCS. This development test path does not establish
clearance approval. No buoy map/truth is sent in the boat mission.

All 26 current boat tests pass. Three consecutive browser-started full slaloms
passed the selected simulator acceptance at a commanded 2.0 m/s target. Measured
speeds, independent hull/finish checks, GCS-loss evidence and physical limits are in [the handoff](milestone1_handoff.md).

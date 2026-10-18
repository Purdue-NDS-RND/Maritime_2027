# Map-based boat navigation with Nav2

Navigation consumes the shared RGB Bearing EKF map. It no longer estimates
marker range independently or sends velocity directly toward buoy waypoints.
Nav2 Smac State Lattice computes a footprint-checked route and Regulated Pure Pursuit
follows it. The mission supervisor selects goals, checks input progress, and
independently checks the commanded hull sweep before releasing commands.
Nav2 checks path validity at 1 Hz, retaining a valid route and replanning when
the goal changes or updated obstacles invalidate it. Soft cost changes alone
do not replace an otherwise valid committed path.

## Run

Start Simulation and Adapter separately. From `autonomy/`:

```bash
make navigation-build
make navigation-test

# One map-frame goal; yaw is radians. Unknown water requires explicit permission.
make run TASK=goal ARGS='--goal 10 0 0 --assume-bounded-water'

# Initial rectangle, relative to the starting boat pose, must be known clear:
# forward [-3,5] m, left [-4,4] m. Mapped obstacles still override it.
make run TASK=gate ARGS='--assume-bounded-water --bootstrap-clear-start --evaluate'
make run TASK=slalom ARGS='--assume-bounded-water --bootstrap-clear-start --evaluate'
```

Use `SCENARIO=gate|slalom BOAT_MODEL=dual WATER=calm make run` in Simulation for
matching course evaluation. Navigation reads no scenario manifest or simulator
truth. `--evaluate` starts an independent simulation-only judge that does. The judge
ends a test if its conservative physical clearance envelope is violated; truth
is never used to generate navigation goals or commands.
One camera remains supported through the mapper's camera roster discovery.

Default operating bounds are `[-5,-12,45,12]` in map metres. Override them with
`--operating-bounds XMIN YMIN XMAX YMAX`. The whole vessel must remain inside.
`--assume-bounded-water` permits planning through unknown cells only within this
boundary. It is a simulation operating assumption, **not observed free water**.
Without this flag, unknown cells remain blocked. Objects undetected by RGB
perception cannot appear in this obstacle map.

`--bootstrap-clear-start` permits up to four observation goals inside the declared
clear rectangle while acquiring range through translation. Relative forward/left
offsets are `(3,1.5)`, `(2,-1.5)`, `(0,1.5)`, `(0,-1.5)` metres. After the first
leg, additional opposing viewpoints are used while the gate is unconfirmed.
Strict uncertainty mode also surveys while active detections lack range; if
that bounded survey is exhausted, it waits for range. Graded mode can continue
toward confirmed course goals while unresolved bearings contribute soft costs.
No rotation-only range initialization is attempted. If useful geometry or
clearance cannot be found,
the boat stops; it does not invent buoy positions or lower uncertainty to fit.

`--external-map` uses an existing shared mapping pipeline; otherwise navigation
reads the camera roster, then starts detection, mapping, and the existing experimental simulation clock
converter. Do not run a second mapper, teleop, or another actuator publisher.
`--plan-only` omits the vehicle bridge and cannot arm or move the boat.

Builds use `maritime-autonomy-nav2:jazzy`, retaining the ordinary mapping image.
The added `BuoyMap.unresolved_world_ids` field requires rebuilding other mapping
and Monitor images before mixing them with this branch.
Session settings and per-process logs go to `Simulation/logs/navigation-*`.
The post-arming wall-time budget defaults to 600 seconds for a goal/gate and
1200 seconds for slalom; override it with `--mission-timeout SECONDS`. Startup
and verified cleanup have separate allowances. Freshness guards remain active
throughout. Ctrl-C stops the command bridge first; a bridge-owned armed session requests
HOLD and disarm before the other processes stop.

## Data and responsibility

| Interface | Use |
| --- | --- |
| `/mapping/occupancy_grid` | Physical occupied cells; unknown elsewhere. Unchanged by navigation. |
| `/mapping/buoys` | Persistent map IDs, categories, metric means, covariance, lifecycle, active unresolved IDs and observation progress. |
| `/mapping/observations` | Unresolved bearings add angular uncertainty costs; strict mode blocks their sectors. |
| `vessel/odometry` | Environment-neutral pose and measured body velocity input. Simulation runner remaps to FCU odometry. |
| `/navigation/planning_grid` | Fully rebuilt, bounded planning grid with physical obstacles, uncertainty, unresolved hazards and mission crossing constraints. |
| `/navigation/odometry` | Planar live state for Nav2; wall-time stamps and `navigation_odom` frame. |
| `/plan` | Smac planned path. |
| `/navigation/cmd_vel` | Nav2's internal body-forward speed and yaw rate; never connected directly to the vehicle. |
| `/navigation/velocity` | Supervisor-gated `TwistStamped`, `base_link`, forward m/s and counterclockwise rad/s. |
| `/navigation/status` | JSON stage, stop reason, target, map session/stamp, unresolved count and mission events. |

The Python costmap adapter keeps physical buoy radius plus 0.15 m clearance
hard. Position uncertainty adds graded costs up to two standard deviations,
using the largest covariance eigenvalue. The soft scores (0-85) are planning
preferences, not calibrated collision probabilities. This intentionally allows
a planner to cross an uncertain region when physical clearance permits it.
Unresolved bearings also contribute angular soft gradients (0-85), without
inventing a range. Under the explicit bounded-water assumption, the boat may
traverse these uncertain regions to gather more parallax. This accepts possible
collision risk from an object whose position is not yet resolved. Use
`--uncertainty-mode hard` to instead exclude both the full two-sigma envelope
and unresolved bearing sectors.
The selected policy is recorded in session settings and `/navigation/status`.
The status `observations` values sum track observation counts for each listed
source camera; they are not per-camera frame counters.

Unresolved bearing sectors follow the mapper's active `unresolved_world_ids`.
A newer observation retains its sector while waiting for its matching map snapshot;
retired unresolved IDs stop contributing sectors. This follows the mapper's
existing five-second unresolved expiry, and does not remove metric obstacles.
Anonymous ambiguous observations retain uncertainty sectors until session reset.
These are soft in graded mode and blocked in strict mode. Unresolved expiry
is not evidence of observed free water.

Tentative, confirmed, stale and inconsistent metric tracks retain hard physical
footprints. The adapter preserves occupied source cells and rebuilds from each
snapshot so moved estimates do not leave ghost footprints. It crops to the
operating region and refines the raster to 0.10 m without clearing any coarse
occupied source cell. This gives usable gate geometry without allocating a
high-resolution grid for the entire 100 m source map. Nav2 applies the 2.2 x
1.2 m polygon footprint and a soft inflation gradient. The hull is not added a
second time to the obstacle radius.

The gate/slalom mission uses retained confirmed/stale shared-map tracks.
Occlusion does not discard a confirmed course landmark; individual uncertainty
continues to grow in the mapper while whole-map acquisition freshness is gated.
Crossing constraints
block shortcuts outside gates or on the wrong side of a turn buoy. Open-water turn goals use a 3 m lateral stand-off. Destination
proximity is required before advancing a course leg. A physically blocked gate still stops the boat. With graded costs, a 3 m gate
can be attempted despite the mapper's 0.25 m uncertainty floor; estimated
physical clearance does not guarantee clearance from the true buoy position.
The optional hard uncertainty mode can legitimately reject that same gate.

When the next confirmed turn or exit gate is missing, graded mode can request
up to four local observation goals: one/two metres farther along the course,
with opposing lateral viewpoints at ±2 m. These are anchored to the start of
that search and remain inside the operating bounds. They do not invent buoy
ranges or advance course events. Nav2 and the hull-sweep guard check each move;
course goals resume as soon as the expected landmark is confirmed. Exhausting
the bounded search stops further observation motion. Strict mode waits instead.


## Frames, time and command transport

Navigation owns `map -> navigation_odom -> base_link`, using the external local
vessel estimate. Currently `navigation_odom` has the same origin as `map`; this
is not a new global localization system or a promise of drift-free odometry.
The Adapter continues to publish only its existing data and static mounts.
The private truth-derived Monitor frames are never navigation pose inputs.

Nav2 uses wall time and live odometry receipt stamps. Mapping uses acquisition
stamps, with the existing experimental FCU-reference/receipt-clock converter
for simulation. Arrival bias remains unmeasured; this is not a hardware-ready
time synchronization solution. Replay through the live navigation runner is
not supported.

The map and physical grid are paired by acquisition stamp in a bounded buffer;
separate topic arrival times do not invalidate the last complete snapshot.
Repeated 10 Hz map publications do not count as new observations. The movement
gate stops when map acquisition progress/receipt exceeds two seconds, odometry
progress exceeds 0.5 seconds, the mapper pauses, or controller commands exceed
0.3 seconds. Brief odometry gaps stop commands while retaining the Nav2 action;
prolonged loss cancels it. Map session changes and timestamp reversal latch a fault until
restart. A three-second sampled hull sweep checks commanded curvature, measured
curvature and straight coasting, using the greater of commanded and measured
speed. It rejects commands entering hard obstacles or unknown cells; the explicitly
selected graded uncertainty costs remain traversable. This horizon and motion settings require boat stopping and
tracking measurements; sampled prediction cannot guarantee behaviour in currents.

The simulation bridge separately requires connected, armed GUIDED state,
forwards body-forward speed plus yaw rate through MAVROS raw BODY_NED setpoints,
and zeros both after 0.5 seconds without a valid command. Body-forward X avoids
Rover's local-NED north/south speed-sign ambiguity. MAVROS performs FLU/FRD and
yaw-rate sign conversion. No MAVROS or simulator imports enter autonomy packages.
Nav2 spin, backup and obstacle-clearing recovery behaviours are not enabled.
The controller aligns heading before driving when the path differs by more
than 0.15 radians, and aligns final goal heading. Retaining valid paths avoids
continually changing the alignment target. Angular motion counts as progress;
hull checks remain active during alignment. Rotation does not supply the
translation needed to initialize buoy range.

The bridge requests 20 Hz LOCAL_POSITION_NED and ATTITUDE_QUATERNION telemetry
and 20 Hz SYSTEM_TIME references for this connection before arming; it restores
their default intervals on exit. Command-smoke durations use simulation time so
slow rendering does not shorten the physical observation window.
With the Adapter enabled, MAVProxy automatic stream requests are disabled;
the Adapter requests the usual 4 Hz baseline once after FCU connection.
This prevents periodic stream-wide resets from overwriting the navigation
intervals. Repeated `odometry_timeout` messages indicate missing or slow pose
delivery; inspect telemetry before changing watchdog thresholds.
Time references match the pose rate so clock interpolation does not hold poses
for a 200 ms simulation-time reference interval during slow rendering.
Live receipt alignment defers transient slope outliers until a valid bracket
arrives, while retaining immediate backward/reset and two-second-gap faults.
It does not extrapolate or change navigation freshness thresholds.
No persistent FCU parameters, boat dynamics or MAVLink ports are changed.
Each RGB detector defaults to one OpenCV thread (`opencv_threads`) to bound
concurrent camera load.

## Inspect and validate

```bash
make -C Monitor build
make -C Monitor rviz-nav
make -C Monitor shell ARGS='ros2 topic echo /navigation/status'

# Moves an initially unarmed simulated boat; stop navigation/teleop first.
make -C Simulation navigation-command-smoke
```

`rviz-nav` uses `map` coordinates and wall time, showing physical occupancy,
planning policy, Nav2 costs, shared buoy estimates, route and hull footprint.
The existing `rviz-sim` view remains a private truth/world inspection tool.

`make navigation-test` runs mission/costmap policy tests, bridge gating tests,
and actual Nav2 servers in isolated ROS domains 97 and 98. The integration fixture uses
synthetic odometry and mapped obstacles to check detouring, map-progress timeout,
blocked-route stopping and session-reset stopping. An additional isolated gate fixture checks the
3 m opening with the actual mapper uncertainty floor. It is software integration
evidence; physical vessel dynamics and live RGB-map accuracy require separate
simulation trajectory evaluation.

Starting configuration: 0.2 m/s desired speed, 1.0 m minimum lattice curve radius,
10 Hz controller/supervisor and 1 Hz path-validity checks. These are provisional simulation
values, not measured hardware limits. Do not claim course acceptance from a
healthy lifecycle node or an ideal kinematic integration test.

Nav2 references: [Smac State Lattice](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/planners_plugins/smac/smac_lattice/configuring_smac_lattice/),
[Regulated Pure Pursuit](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/configuring_regulated_pp/).

## Validation record (2026-10-18)

| Check | Measured result |
| --- | --- |
| Simulation and Monitor `make validate` | Passed syntax, assets, pinned-source and Compose checks. |
| `make -C autonomy navigation-test` | 34 unit tests, 5 bridge tests, and actual Nav2 detour/gate fixtures passed. Minimum physical hull clearance: 1.09 m detour, 0.45 m three-metre gate. |
| Existing live mapping regression | 9 tests passed using a separate Nav2-based mapping-view image. |
| Root boundary tests | 13 passed; one ROS-only host test skipped. |
| Monitor smoke, isolated domain 100 | Cross-container custom messages, image payloads, TF, CLI deserialization and rate measurements passed with the extended `BuoyMap`. |
| `make -C Simulation verify-rgbd` | Full RGB-D, scenario, boundary, MAVROS and original-control regression passed. |
| Telemetry ownership regression, with RViz open | Adapter tests: 11 passed; bridge tests: 5 passed; lifecycle `default_adapter,signal_int` passed. A 45 s live capture measured 8.42 Hz clock-aligned odometry, maximum gap 0.187 s, and no odometry timeout. The complete dual-camera gate retest passed in 218 s with 0.25 m minimum conservative buoy clearance, 0.62 m stern exit clearance, and verified HOLD/disarm. Run `navigation-20261018-115751`; probe `logs/nav-telemetry-gate-probe.json`. |
| `make -C Simulation navigation-command-smoke` | Forward movement at east/south headings, both yaw-rate signs, stopping, HOLD and disarm passed. Maximum measured stopping travel was 0.44 m after a 0.3 m/s command. |
| Live RGB-map 3 m gate, dual cameras, calm water | Passed in 126 s wall time. Minimum clearance from conservative 0.6 m buoy envelopes: 0.23 m; whole-stern exit clearance: 0.71 m. No evaluator clearance violation. HOLD/disarm verified; runner exit code 0. Run `navigation-20261018-052923`. |
| Live RGB-map slalom, dual cameras, calm water | Passed all six course events and all eight required-side checks in 852 s wall time. Minimum clearance from conservative 0.6 m buoy envelopes: 0.68 m; whole-stern exit clearance: 0.62 m. No evaluator clearance violation. HOLD/disarm verified; runner exit code 0. Run `navigation-20261018-051135`. |

Local, uncommitted evidence is under `Simulation/logs/nav2-validation/` and
`Simulation/logs/navigation-*`. Mapping regression used
`AUTONOMY_IMAGE=maritime-autonomy-nav2:jazzy` as the optional mapping-view Docker
build argument and `MAPPING_IMAGE=maritime-mapping-view-nav2:jazzy` for the test;
the ordinary mapping images were retained. These results establish simulation
behavior only; hardware timing, transport and disturbance rejection remain
separate validation work.

# Gate and Dodge navigation

The optional `maritime_navigation` package uses both calibrated RGB cameras to
find the entry gate, pass red buoys on their left and green buoys on their right,
and clear the exit gate. The entry gate establishes the course axes. Buoy
coordinates, physical identities and scenario manifests are not navigation
inputs. The existing `slalom` scenario provides gate A, four alternating turns,
and gate B; `gate` provides the standalone first challenge. The gate scenario
now places green on the left and red on the right for forward traversal.

This implements the gate and Dodge sequence described on pages 5-7 of the
AIMM-ICC Competition Course Details (December 13, 2025). Course dimensions in
simulation are provisional. Leaving a real dock, competition deployment,
natural color detection, GPS independence and other challenges are outside the
validation of this simulation implementation.

## Run

Build navigation from `autonomy/` once:

```bash
cd autonomy
make navigation-build
```

Start Simulation and the Adapter in one terminal:

```bash
cd Simulation
SCENARIO=slalom BOAT_MODEL=dual WATER=calm make run
```

Start navigation in a second terminal:

```bash
cd autonomy
make run ARGS=--evaluate
```

Simulation starts its Adapter by default, and starts no autonomy application.
The old placeholder is no longer part of the Simulation stack.
For the standalone gate, use `SCENARIO=gate` in Simulation and
`make run TASK=gate ARGS=--evaluate` in autonomy. The runner requires a
healthy simulator and Adapter. It waits for an observed gate before requesting
GUIDED and arming an initially disarmed boat. It sends ENU desired velocity at
up to 0.65 m/s. Completion, interruption and session timeout invoke a zero
command, HOLD and disarm. External mode changes end the command session.
Ctrl-C stops this session; use `make down` to stop Simulation separately.
Start each complete attempt from a fresh simulator with the gate ahead of the
boat. A new session after passing the gate waits for another gate ahead.

Logs and optional `result.json` are in `Simulation/logs/navigation-<timestamp>/`.
The independent judge records actual buoy poses and the boat trajectory, checks
all buoy side crossings and conservative footprint clearance, and requires the
complete gate/turn/exit event sequence with observations from both cameras.
A successful process launch or healthy container is not a navigation pass.

`make navigation-test` in `autonomy/` runs the course-planning and existing autonomy boundary
tests on the host, plus RGB geometry and command-gate tests in isolated containers.
It requires the built autonomy and evaluation images but no running simulator.

## Inputs and limits

- `/sensors/camera_0/color/{image_raw,camera_info}` and the corresponding
  `camera_1` topics, plus their calibrated `base_link` optical transforms.
- `vessel/odometry` is the environment-neutral navigation input. The simulation
  runner remaps it to `/mavros/local_position/odom`; navigation has no MAVROS,
  Gazebo, FCU transport or ground-truth dependency. Its generic output is
  `/navigation/velocity` (`TwistStamped`, map/ENU) and its progress output is
  `/navigation/status` (`String` JSON).
- Metric range comes from PnP on the existing 0.50 m ArUco faces, with IDs 1/2
  denoting red/green categories. Repeated IDs are associated by observed
  position, never treated as unique buoy identities. These fiducials and known
  size are a simulation perception assumption, not a natural-buoy detector.
  The existing bearing-only mapper is unchanged.
- Live image and odometry **receipt times** are paired within 0.25 seconds.
  Processing drops frames older than 0.5 seconds. This approximation is for slow
  live simulation; it is not acquisition-time synchronization or a replay path.
- Missing camera data (1.5 s) or odometry (0.5 s) causes zero desired velocity.
  Missing marker observations (8 s) also stops motion, except for the bounded
  clearance leg after entering an already observed gate. That leg uses fresh
  odometry and requires the conservative hull footprint to fit inside the
  observed gate; it lets the stern clear after the markers leave the forward cameras. No blind forward search is performed. Gates must
  be 2.6-6 m wide and approximately perpendicular to the initial boat heading.
  Turn count defaults to four; the gate-only task configures zero.
- The course is traversed in the direction established by the first gate. The
  planner retains observed landmarks, selects new targets only from landmarks
  observed within the last three seconds, and commits to each target while passing
  it. It is intended for the forward, ordered buoy course, not arbitrary obstacle
  avoidance or a general route planner.
- The simulation command bridge separately gates on connected, armed GUIDED
  state, bounds commanded speeds, and zeros commands after 0.5 seconds without
  a navigation message. It forwards velocity through `/mavros/setpoint_raw/local`
  with yaw and yaw rate ignored, selecting Rover's heading-and-speed control.
  Sending velocity plus yaw rate through the standard velocity plugin instead
  selects Rover's turn-rate control, whose NED-X sign can reverse the vessel on
  southbound course segments. It runs only with explicit simulation environment flags.
  Do not run teleop or another setpoint publisher during this command session.

## Validation

Navigation acceptance on October 17, 2026 used `BOAT_MODEL=dual WATER=calm`:

- Standalone gate: both buoy sides and the whole-vessel crossing passed;
  minimum conservative footprint clearance was 0.28 m.
- Full slalom: gate A, four turns and gate B passed the independent trajectory
  judge; minimum conservative clearance was 0.44 m, and the entire conservative
  footprint cleared the exit plane by 0.79 m. Both cameras contributed more than
  1,250 marker observations.
- Armed interruption and normal completion both verified HOLD and disarm.
- `make dual-camera-smoke`: both exact RGB-D streams and mount TF passed,
  with 30.3 Hz measured using source timestamps and the expected gate marker
  visible in each camera.
- `make validate` in Simulation, `make navigation-build` and `make navigation-test` in autonomy, repository
  boundary tests, and the complete `make verify-rgbd` suite passed. The latter
  includes original ArduPilot travel, stopping, return and disarm behavior.

The validation above describes the navigation algorithm; startup ownership is now
Simulation + Adapter in `Simulation/` and explicit navigation in `autonomy/`.

Run-specific evidence remains under `Simulation/logs/`; no generated logs or
scenario files are committed. To render a judged trajectory locally:

```bash
MPLCONFIGDIR=/tmp/navigation-matplotlib python3 tests/evaluation/plot_navigation.py \
  logs/navigation-<timestamp>/result.json
```

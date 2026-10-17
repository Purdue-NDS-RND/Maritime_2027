# Live Bearing EKF Buoy Mapping while teleoperating

This is an optional foreground session on top of the existing simulation.
It starts the production ArUco detector and Bearing EKF buoy mapper, plus separate simulation
monitoring tools. It never starts, stops, arms, or drives the simulator.

## Run

Build once, or after changing the autonomy image/dependencies:

```bash
make -C autonomy mapping-build
```

Use the usual simulator and teleop terminals, unchanged:

```bash
cd Simulation
SCENARIO=gate make run
```

```bash
cd Simulation
make teleop
```

In a third terminal, from the repository root:

```bash
make -C autonomy mapping
```

The foreground session opens a top-down popup. Close it or press Ctrl-C in its
terminal to stop only its detector, mapper, clock adapter, and viewer. The
simulator, Adapter, bootstrap, and separate teleop session remain running.
Starting it again creates a fresh mapping session and empty map. One managed
mapping session per ROS domain is enforced by its Docker container name.
Do not also launch a manual detector/mapper on the same topics/domain.

For an additional RViz view, use the existing command:

```bash
make -C Monitor rviz-sim
```

The simulation preset includes **RGB map estimates (provisional truth alignment)**.
It receives standard MarkerArray messages, so the neutral Monitor image does not
need custom autonomy messages or an autonomy workspace overlay. Current RViz
presets are mounted from the checkout; rebuilding Monitor is unnecessary for
preset changes.

Run without a popup, retaining the RViz overlay:

```bash
make -C autonomy mapping VIEW=none
```

Open only a popup for a running managed session:

```bash
make -C autonomy mapping-view
```

Set the same `ROS_DOMAIN_ID` on Simulation, teleop, autonomy, and Monitor if using
a nondefault domain. The default is 0. Popup mode requires a local X11/XWayland
`DISPLAY` and `xauth`, as does the existing Monitor GUI workflow. It copies only
the current display cookie into a temporary read-only mount, removed on exit.
It does not change X server access control. Headless mode needs no display.

## What to watch

* **Top-down map:** boat pose/path, estimated buoy means and mean trails, and
  covariance ellipses with 3-sigma principal radii. Tentative/stale estimates use
  dashed ellipses. Black crosses show simulator buoy positions after the
  provisional frame alignment described below. Each track retains its world ID.
* **Mean history:** map X and Y of each estimate; solid X and dashed Y. The
  horizontal axis is source seconds since that track's first metric record.
* **Variance history:** marginal X/Y variances in square metres. These are
  estimated uncertainty, not measured squared error or guaranteed coverage.
* **Status:** unresolved tracks, solver/filter evidence, stale inputs, mapping
  faults, and clock mode. Before sufficient motion, seeing detections but no
  metric tracks is normal. A stopped image stream retains the last result and
  reports it as stale. The plot keeps bounded history (600 samples per track,
  1,500 boat samples) and refreshes about twice per second.

Move across the buoy's line of sight, rather than just turning in place. The
existing mapper requires at least four useful views, a 1 m baseline, and 5 degrees
of parallax before initialization. It then needs three later consistent selected
updates for confirmation. Occlusion can make a confirmed track stale; its ID and
position persist for reacquisition. Press `a` in the plot to disable auto bounds
before using toolbar zoom/pan; press it again to resume automatic bounds.

## Explicit timing and frame assumptions

The production mapper still requires acquisition-time pose brackets and never
estimates clock offsets from message arrivals. Existing simulation bringup,
MAVROS configuration, FCU transport, and camera topics are unchanged.

The default `POSE_CLOCK=receipt` is an **experimental simulation monitoring
adapter**, implemented under Monitor. It pairs the source header stamp of each
`/mavros/time_reference` (requiring `source=fcu`) with the latest received `/clock`
value. It buffers odometry until enclosing references exist and interpolates
timestamps into `/monitor/mapping/vessel/odometry`. It preserves pose values,
frames, and original topics. References at 1 Hz add roughly one reference
interval of display/mapping latency; this session gives the mapper a 2 s input
wait while retaining its 0.3 s pose-bracket gap limit. History and pending queues
are bounded. Reset/gap/rate faults latch until the session is restarted.

Receipt delay and bias are unmeasured. A provisional 20 ms timing uncertainty
floor inflates pose covariance using recorded twist magnitude; this is a modeling
assumption, not a measured latency bound. This mode is useful for observing
convergence during teleop, not certifying timestamp accuracy. It consumes no
images, buoy positions, or simulator ground truth. Live operation requires
`/clock`, MAVROS odometry, and FCU time references; without them it waits visibly.

For compatible source clocks, or a separately verified constant offset:

```bash
make -C autonomy mapping POSE_CLOCK=source
make -C autonomy mapping POSE_CLOCK=source POSE_TIME_OFFSET_S=-123.45
```

The second command is only an example: **source pose stamp + offset = image
stamp**. Do not copy its numeric value as a calibration. `POSE_TOPIC` selects an
alternative compatible `map -> base_link` odometry topic. Use the same settings
for `mapping-view`. Manual offsets cannot be combined with receipt mode.

Ground-truth buoy positions are in Gazebo `world`; estimates are in MAVROS
`map`. They are not assumed identical. The viewer freezes a planar rigid
transform from one time-matched truth/mapper boat pose pair, including yaw, then
uses it only for display. Subsequent time-matched boat-position discrepancy is
shown rather than silently realigning to hide drift. Missing pose brackets hide
the truth overlay; a truth-clock/reset fault invalidates it until viewer restart.
This is provisional alignment, not a surveyed accuracy reference. Marker-centre
versus buoy-centre offsets and pose/clock errors can produce visible differences.

Truth subscriptions, frame alignment, plots and world-frame RViz overlays exist
only in `Monitor/tools/mapping_view.py`. The mapper receives RGB detections,
calibration, mounting TF, and vessel poses. No truth-derived TF is published to
the production graph. The only visualization output is the private
`/monitor/mapping/markers` topic.

## Validation

```bash
make -C Simulation validate
make -C autonomy mapping-test
make -C Monitor validate
```

The live test publishes real RGB ArUco images, calibration, static TF, one-Hz FCU
time references, and a moving vessel with a deliberately different-rate epoch
clock. It launches the production ROS detector/mapper, requires a confirmed
stable position, checks clock reset rejection, exercises translated/rotated
truth-display alignment, and renders the plot. A deliberately false truth buoy
checks that truth cannot drive the estimated mean. The test uses an isolated
container/network and writes a preview to
`Simulation/logs/live-mapping-validation/live-mapping.png`.

These checks establish controlled software behavior. A complete manually driven
Gazebo run, measured live clock bias, and on-water covariance calibration remain
separate acceptance evidence.

Development verification passed: five live-tool tests (including a real Tk popup
on an isolated virtual display), all 78 existing benchmark regression tests,
Simulation static validation, and Monitor validation. An isolated domain-95
headless session also started and stopped with both production nodes exiting
cleanly; existing simulation services were left running as found.

# Simulation RViz validation — 2026-10-15

Scope: Monitor-only visualization on `feature/monitor-rviz-simulation`.
Simulator assets, Adapter interfaces, navigation TF, dynamics and ports are unchanged.

## Passed

- `make -C Simulation validate`: script, asset, scenario and SDF checks.
- `make -C Monitor validate`: shell/Python syntax and Compose configuration.
- `make -C Monitor build`: image includes the helper and simulation preset.
- `make -C Monitor smoke`: cross-container text, full 1280×720 RGB/depth and TF delivery.
- Fresh `gate` scenario, `make -C Simulation sensor-smoke`: 100 exact RGB/depth/
  CameraInfo triples at **30.30 Hz**, marker identities, depth and public camera TF.
- `make -C Simulation mavros-smoke`: connected telemetry, GUIDED velocity, motion,
  zero-velocity stop, HOLD and disarm, with the Monitor view running.
- `Monitor/tests/simulation_view_probe.py` against the GUI session: world poses
  agree with boat and both buoy odometry; the private camera chain connects to
  world; preview geometry agrees with CameraInfo; RGB colors and viewing outline
  are populated. Clearing the probe's TF cache recovers the complete chain through
  repeated static transforms. The helper publishes neither `/tf` nor `/tf_static`.
- Visual inspection: world origin/grid, named buoy visuals, boat, attached RGB
  plane and lower-left full-resolution image. Preview is 80×45 at up to 4 Hz.
- Isolated final helper SIGTERM check: exit 0, without a shutdown traceback.
- Forced RViz termination also stops the helper and removes the tool container.
  RViz itself returned a segmentation fault on forced SIGTERM in this environment;
  this was not a normal window-close test.

## Incomplete full regression

`make -C Simulation verify-rgbd` was attempted. Buoy tracking passed 3,499 facing
checks, including late spawns and repeated colors. In the first (`one`) scenario,
the Gazebo source probe reported 120 exact RGB/depth pairs at 30.30 Hz simulated
time (about 20 Hz wall callback cadence), then aborted on shutdown with
`terminate called without an active exception`. The script stopped and cleaned
up; the later scenarios and original-control test did not run. This is **not** a
passing full-suite result. No production test or acceptance threshold was changed.

An earlier sensor smoke in the user's existing gate session found 0/10 buoy
observations: the boat was already beyond the gate. The fresh gate run above
passed. The simulator was restored to `gate` afterward.

## Local evidence (ignored runtime output)

- `Monitor/logs/rviz-simulation-gate.png`: validated rendered view.
- `Monitor/logs/rviz-scene-probe.log`: live scene and TF-recovery probe.
- `Monitor/logs/rviz-monitor-smoke.log`: cross-container regression.
- `Simulation/logs/rviz-sensor-smoke.log`, `rviz-mavros-smoke.log`.
- `Simulation/logs/verify-rgbd-monitor.log`: full-suite attempt and shutdown abort.

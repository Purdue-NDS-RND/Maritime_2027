# Container Split Verification — 2026-09-12

The extraction separates `Simulation/`, `Adapter/`, and `autonomy/` while retaining
the existing simulation commands. This record describes desktop verification,
not Jetson/ZED or real-vessel readiness.

## Results

- `make validate`: passed, including four Compose contract tests and Docker-backed
  Gazebo SDF validation. Protected model/parameter hashes and upstream source pins
  remain unchanged.
- Both adapter and autonomy images built successfully. Inspection of the built
  images confirmed that autonomy has MAVROS without `ros_gz_bridge`, and the
  adapter has `ros_gz_bridge` without the MAVROS server package.
- `make boundary-smoke`: passed in the one-buoy and gate scenarios. Camera and
  flight-controller messages reach autonomy, and perfect pose TF stays on the
  evaluation-only topics. MAVROS fixed coordinate-convention transforms are
  allowed on shared TF alongside camera extrinsics.
- `make mavros-smoke`: passed in the one-buoy scenario, including connected
  telemetry, mode/arm services, a bounded RC pulse, movement, settling, and disarm.
- `make smoke`: passed independently in the buoy-free RGB-D world, including
  GUIDED travel, HOLD, return to the starting area, and confirmed disarm.
- One-buoy sensor evaluation passed on individual runs, including 100 exact
  RGB/depth pairs, detection, depth accuracy, calibration, truth, and evaluation
  TF. This was not a consistently passing throughput result.
- Gate and one-buoy Gazebo source checks passed at approximately 30.30 Hz in
  simulated time. Seeded multi-buoy startup exposed all four expected buoy models.

## Unresolved Regression

`make verify-rgbd` is **not green**. The Python/OpenCV evaluator intermittently
falls below its existing 8.00 synchronized-pairs/sec threshold. Observed standard
evaluator rates ranged from 6.71 to 9.20 Hz; the separate gate evaluation measured
7.58 Hz and failed. Source-camera cadence passed, but that does not override the
evaluator failure. Full gate sensor assertions after the rate check are therefore
not verified by that failed run.

The detector, sensor settings, acceptance thresholds, and boat dynamics were not
changed to hide this failure. A single-OpenCV-worker experiment was inconclusive
and was not committed. Follow-up should profile/reproduce evaluator throughput
under the split deployment before treating the full suite as passing.

## Integration Issues Resolved

- The old cached ROS image used MAVROS 2.14.0; the fresh image installed 2.15.1.
  Its changed namespace behavior initially produced `/mavros/mavros/...`.
  The shared launch now preserves the public `/mavros/...` interfaces.
- Separate IPC namespaces initially prevented cross-container sensor delivery
  despite topic discovery. Both trusted ROS services now use shared host IPC;
  the boundary smoke test verified actual delivery after the change. See
  [deployment guidance](../../deployment/README.md) for the isolation tradeoff.

The independent remaining-checks run finished with one failure: gate evaluator
throughput. Gate boundary checks, seeded-multi startup, and the original control
regression passed. This does not turn the failed full-suite result into a pass.

Complete runtime output is kept locally in ignored `Simulation/logs/`, including
`verify-container-split.log` and `split-remaining-checks.log`. These logs are not
committed project source. A read-only code review found no blocking implementation
defects; that review does not replace the runtime results above.

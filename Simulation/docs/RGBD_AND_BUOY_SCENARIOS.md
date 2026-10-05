# RGB-D and ArUco buoy scenarios

Start a ROS scenario from `Simulation/`:

```bash
SCENARIO=one make run
SCENARIO=gate make run
SCENARIO=multi BUOY_SEED=42 make run
SCENARIO=repeated_red make run
```

The ROS profile starts Gazebo/SITL, the Simulation Adapter, and the temporary
autonomy bootstrap. The Adapter owns MAVROS on `udp://:14552@`, the root
`/mavros/...` namespace, camera bridges, and readiness diagnostics. The
bootstrap is infrastructure only: its mission readiness is false and it sends
no vehicle commands.

## Public camera boundary

The one simulated RGB-D source is a generic test camera, not a ZED X Mini
replica. Its public interfaces are:

| Topic | Meaning |
|---|---|
| `/sensors/camera_0/color/image_raw` | `rgb8` or `bgr8` color |
| `/sensors/camera_0/depth/image_rect_raw` | registered `32FC1` depth in metres |
| `/sensors/camera_0/color/camera_info` | color/depth calibration and dimensions |

The shared static chain is `base_link -> camera_0_link ->
camera_0_optical_frame`. Private Gazebo `zed2i_*` names are not public
interfaces. Perfect boat and buoy pose remains under
`/blueboat/ground_truth/...` for simulation evaluation only.

## Explicit evaluation

While a scenario is running:

```bash
make sensor-smoke
make boundary-smoke
make mavros-smoke
```

These commands run the dedicated `Simulation/tests/evaluation/` image only when
explicitly invoked. `mavros-smoke` is simulation-guarded, requires the SITL
endpoint, confirms GUIDED mode before arming, then sends a bounded MAVROS
velocity setpoint and verifies a zero-velocity stop, HOLD, and disarm cleanup.
Never use it against hardware.

`make verify-rgbd` runs scenario and control regressions, including two visible
red-category entities in `repeated_red` with distinct instance identity. The
RGB-D evaluator's
8.00 synchronized-pairs/sec threshold remains unchanged; a lower measured rate
is a failure, not evidence of a successful run.

## Limitations

There is no perception, mapping, navigation, mission system, real autonomy
application, hardware Adapter, or vessel readiness claim. Hardware work is
deferred until its platform, transport, and signed camera evidence are known.

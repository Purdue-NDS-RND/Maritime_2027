# RGB-D and ArUco buoy scenarios

## Start a scenario

```bash
SCENARIO=one make run
SCENARIO=gate make run
SCENARIO=multi BUOY_SEED=42 make run
```

`SCENARIO` enables the ROS Compose profile automatically. Gazebo, BlueBoat,
ArduPilot SITL, MAVProxy, MAVROS, the ROS bridges, and static TF publishers all
start under the single foreground command across three containers: simulation,
adapter, and autonomy. MAVROS runs in autonomy; bridges and evaluation clients
run in the adapter. Plain `make run` remains the
original non-ROS simulation. `ROS_SIM=1 WORLD=blueboat_rgbd_base.sdf make run`
starts the camera boat without buoys.

Scenario JSON files are safe to edit. Every buoy defines a stable `buoy_N`
name, matching ArUco ID, nominal pose, and jitter bounds. With no seed the
nominal layout is exact. An integer `BUOY_SEED` produces repeatable independent
jitter while the renderer rejects overlaps and invalid test positions. The
resolved world and pose manifest are written to `logs/generated-worlds/`.

## Camera

The only simulated imager is Gazebo's built-in `rgbd_camera`; it is not a
stereo pair and no disparity is calculated. It is mounted at `(0.35, 0, 0.40)`
metres in `base_link`, level and forward. The output is 1280×720 at 30 Hz with
approximately 110°×70° field of view, 0.30–20 m clipping, explicit pinhole
intrinsics, and ideal deterministic depth. Treat it as a bounded generic RGB-D
test source. It does not model either of the two planned ZED X Mini cameras or
their combined physical configuration.

ROS topics:

| Topic | Type |
|---|---|
| `/blueboat/camera/rgb/image_raw` | `sensor_msgs/msg/Image` (`rgb8`) |
| `/blueboat/camera/depth/image_rect_raw` | `sensor_msgs/msg/Image` (`32FC1`, metres) |
| `/blueboat/camera/camera_info` | `sensor_msgs/msg/CameraInfo` |
| `/clock` | `rosgraph_msgs/msg/Clock` |
| `/tf_static` (camera extrinsics only) | `tf2_msgs/msg/TFMessage` |
| `/blueboat/ground_truth/tf`, `/blueboat/ground_truth/tf_static` | `tf2_msgs/msg/TFMessage` (evaluation only) |
| `/blueboat/ground_truth/odometry` | `nav_msgs/msg/Odometry` |
| `/blueboat/ground_truth/buoy_N/odometry` | `nav_msgs/msg/Odometry` |

The evaluation TF tree is `world -> odom -> base_link -> zed2i_camera_link ->
zed2i_left_camera_optical_frame`. Gazebo owns its perfect dynamic
`odom -> base_link`, published only on `/blueboat/ground_truth/tf`.
The sensor evaluator remaps its listener to the evaluation TF topics.
The adapter publishes only camera extrinsics on shared `/tf_static`; MAVROS also
publishes fixed ENU/NED and FLU/FRD convention conversions. No perfect world/odom
pose is supplied to navigation. MAVROS's local-position TF output remains disabled
as before; estimated navigation-frame integration is future autonomy work.
Buoy truth is deliberately not added to TF and is never fed into control.
The `zed2i_*` names are retained implementation identifiers from the initial
simulator model; they do not mean that the simulated sensor represents the
project's target ZED X Mini hardware.

## MAVROS

SITL sends a dedicated MAVLink stream to UDP 14552. MAVROS in the autonomy container listens with
`udp://:14552@` in namespace `/mavros`, target system/component 1/1, MAVLink
v2, and no GCS forwarding. Existing UDP 14550 and 14551 outputs are unchanged.

## Evaluation commands

While a scenario is running:

```bash
make sensor-smoke
make boundary-smoke
make mavros-smoke
```

The sensor test collects 100 exact-stamp RGB/depth pairs, checks calibration,
TF, truth, marker size/detection, and geometric depth error. The full verifier
measures RGB and depth source cadence from Gazebo timestamps (27–33 Hz accepted
for the configured 30 Hz sensor), separately from the slower Python/OpenCV evaluator
throughput. Its ArUco detector exists only for this explicit test. The MAVROS test checks telemetry,
mode and arm services, sends a bounded 0.5-second manual RC pulse, neutralizes,
checks truth motion and settled speed, and disarms even on failure.

The read-only boundary test runs from the autonomy container. It verifies that
camera data crosses from the adapter, FCU state appears at `/mavros/state`, and
shared TF contains camera extrinsics without perfect simulator vessel poses.
This test is injected from the host; evaluation code is not shipped in autonomy.

`make verify-rgbd` launches all scenarios, runs these checks where applicable,
repeats the original pymavlink control regression in the buoy-free RGB-D world,
and cleans up each run.

## Deliberate limitations

These worlds contain no perception pipeline, continuous marker detection,
mapping, localization, navigation, autonomy, mission system, GCS, point cloud,
right image, stereo reconstruction, or disparity. Ideal Gazebo depth also does
not model sunlight, water reflections/refraction, spray, lens contamination,
exposure behavior, or real ZED stereo failure modes.

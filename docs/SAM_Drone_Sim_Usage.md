# SAM drone simulator usage

The drone simulator runs a stock Iris quadcopter in Gazebo Harmonic with
ArduCopter software-in-the-loop (SITL). The Iris has a fixed downward-facing
RGB camera. Its view points straight down in level flight and tilts with the
airframe. The simulator runs independently of the boat and GCS.

## Start the simulator

**Terminal 1**, from the repository root:

```bash
cd simulation
make drone-build
make drone-run
```

The build uses the pinned Gazebo and ArduPilot sources in the local
`maritime-sim:latest` image. If that image is missing, build it with
`make build` from `simulation/` first. Rebuild the drone image after changing
the world or camera. Otherwise, `make drone-run` is enough.

Startup runs headless and waits for advancing camera frames and an
ArduCopter heartbeat. The launcher prints the run directory and MAVLink address.

**Optional Gazebo window**, in another terminal from the repository root on a
local X11 desktop:

```bash
cd simulation
make drone-gui
```

Open **Image Display** in Gazebo and select `/iris/down_camera/image` to see the
Iris camera feed.

## Fly and capture a frame

**Terminal 2**, from the repository root:

```bash
cd simulation
make drone-console
```

Enter these commands one at a time at the MAVProxy prompt. Wait for the
pre-arm checks and confirm that the motors are armed before sending takeoff.

```text
mode guided
arm throttle
takeoff 5
```

While the Iris is hovering above takeoff, use **Terminal 1** to save a PNG and
check that marker ID 0 is visible:

```bash
make drone-camera MARKER_ID=0
```

Omit `MARKER_ID` to save the next frame and print any IDs detected. You can
request IDs 24 or 25 when flying over the corresponding tower.

An external MAVLink client can connect to TCP `127.0.0.1:5764`. Use one client
at a time. Set `DRONE_MAVLINK_PORT` when starting the simulator to override the
host port.

To finish, enter `mode land` in MAVProxy and wait for disarm, then run
`make drone-down` in Terminal 1. Landing uses ArduCopter's ordinary LAND mode.
The takeoff tag is available as a visual reference.

## Course layout and marker sizes

The flat world uses the east and north coordinates from the
[full competition course](../simulation/scenarios/competition.json). The six
competition props are present. All 23 buoy positions use upward-facing ground
tags. Both Evade detector (LiDAR) towers carry tags centered on their roofs.

| ArUco ID | Location | Square including white margin | Black-bordered tag |
| --- | --- | ---: | ---: |
| 0 | Takeoff at the world origin | 2.00 m | 1.50 m |
| 1–23 | Buoy positions in course-file order | 0.48 m | 0.36 m |
| 24 | Left Evade tower roof | 0.48 m | 0.36 m |
| 25 | Right Evade tower roof | 0.48 m | 0.36 m |

The markers use OpenCV's `DICT_4X4_50` dictionary. The course squares match
the simulated buoy's 0.48 m diameter. The tower roofs are 1.50 m above the
ground.

## Camera data and logs

- `/iris/down_camera/image` publishes 1280 × 960 RGB at 15 Hz in Gazebo
  simulation time.
- `/iris/down_camera/camera_info` publishes the camera intrinsics. The fixed
  camera has a 90° horizontal field of view.
- `simulation/logs/drone-sitl/latest-run.txt` names the latest run directory.
  Each run starts with fresh SITL state and stores `gazebo.log`, `sitl.log`,
  camera snapshots, and `markers.csv`. The CSV records each marker's ID,
  source object, east/north/up coordinates, and black-bordered tag width, in
  metres.
- Use `make drone-logs` from `simulation/` to follow startup messages. If
  startup fails, inspect `gazebo.log` and `sitl.log` in the latest run directory.

## Verified behavior

All 26 generated marker textures decoded with the expected IDs, and their
placements matched the course coordinates and tower roofs. In SITL at about
5 m above takeoff, the downward camera decoded the takeoff tag, resized Dodge
gate tags, and both tower roof tags. The Iris returned to takeoff, landed, and
disarmed. The [milestone results](milestone1.md#standalone-iris-survey-simulator)
record the validation scope and log locations.

See the upstream [ArduPilot Iris SITL workflow](https://docs.ardupilot.org/dev/docs/sitl-with-gazebo.html)
and [Gazebo Harmonic guide](https://gazebosim.org/docs/harmonic/getstarted/) for
the underlying simulator tools.

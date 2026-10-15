# ROS 2 Monitor

Independent ROS 2 Jazzy tools for simulation, hardware, and bag playback. The
monitor starts no simulator, bridge, MAVROS, autonomy node, or FCU connection.
Each invocation runs a disposable container; multiple terminals can coexist.

## Start

From the repository root on native Linux with Docker Engine and Compose:

```bash
cd Monitor
make build     # First setup, and after updating this directory
make shell
# Inside the shell (ROS is already sourced):
ros2 topic list
ros2 topic info /some/topic --verbose
ros2 topic echo /some/topic
ros2 topic hz /some/topic
ros2 node list
```

All following host commands run from `Monitor/`. From the repository root, use
`make -C Monitor TARGET` instead. Running `make` alone prints help. The first
session also builds the image if absent.

Start your target ROS system separately, then open tools in additional terminals:

```bash
make topics            # Quick topic listing
make nodes             # Quick node listing
make rviz-sim          # Simulation or bag playback publishing /clock
make rviz              # Hardware / wall time
make graph             # rqt_graph
```

Each shell or GUI is independent. Exit Bash with `exit` or Ctrl-D; close a GUI
window to end its container. You do not need a separate monitor shutdown command.
These commands do not start or stop the target ROS system.

## Settings and arguments

Most runs need only the right clock mode and the same ROS domain as the target:

```bash
make rviz-sim ROS_DOMAIN_ID=0
make shell ROS_DOMAIN_ID=0
make rviz ROS_DOMAIN_ID=12 LIBGL_ALWAYS_SOFTWARE=1
```

| Setting | Default | Purpose |
|---|---|---|
| `ROS_DOMAIN_ID` | `0` | Match the target ROS graph. |
| `USE_SIM_TIME` | `false` | RViz clock; `rviz-sim` always forces `true`. |
| `LIBGL_ALWAYS_SOFTWARE` | `0` | Set `1` if GPU rendering fails. |
| `ARGS` | Empty | Extra arguments, or the command for `make shell`. |

Arguments use normal shell quoting inside the Make variable:

```bash
make shell ARGS='ros2 topic echo /mavros/state --once'
make shell ARGS='ros2 run tf2_ros tf2_echo base_link camera_0_link'
make topics ARGS='--no-daemon'
make rviz-sim ARGS='-d /logs/my-view.rviz'
make build ARGS='--no-cache'
```

`make build` updates the image; launch a new tool session to use it. Existing
sessions keep their original image. For less common tools, the launcher remains
available: `./scripts/monitor gui COMMAND [ARG ...]` or
`./scripts/monitor shell COMMAND [ARG ...]`. All existing launcher environment
settings also work with Make.

GUI modes need a local X11 or XWayland display and host `xauth`. The launcher
copies the current display cookie into a private temporary file and removes it
when the session ends. It does not change the X server access policy. Shell mode
needs neither display nor xauth. Sessions use the host user's UID/GID; GUI modes
map `/dev/dri` and its video/render groups when available. Set
`LIBGL_ALWAYS_SOFTWARE=1` to skip GPU mapping and use Mesa software rendering.
NVIDIA-specific runtime integration is not configured.

RViz starts in `base_link` with a metre grid, TF axes, and the public camera color
view enabled. The preset uses the shared Adapter contract, so the same names work
for simulation and conforming hardware:

| Display | Topic / frame | Starts enabled |
|---|---|---|
| TF and metre grid | `base_link`, `/tf`, `/tf_static` | Yes |
| Camera 0 RGB | `/sensors/camera_0/color/image_raw` | Yes |
| Camera 0 depth | `/sensors/camera_0/depth/image_rect_raw` | No |
| FCU odometry trail | `/mavros/local_position/odom`, fixed frame `map` | No |

Camera subscriptions use best-effort, volatile QoS with queue depth 1. Depth uses
a fixed 0–20 metre grayscale display range; change Min/Max Value for your scene.
This is a viewing scale, not a sensor limit. Depth opens an additional pane when
enabled; resize or float the pane as needed. For a second camera, duplicate a
display and change `camera_0` to `camera_1`.

Enable the odometry display and change Global Options → Fixed Frame to `map`
to inspect the FCU position/orientation trail (up to 50 samples). The Adapter does
not publish a dynamic `map → base_link` transform, so camera/body TF may appear as
a separate tree in this view. No transform is fabricated to join them. The saved
Top down view and toolbar Measure tool help inspect planar geometry and distances.
The preset includes no goal-setting tools or simulation-truth subscriptions.
For targets outside the Adapter contract, change the topics and fixed frame.
Use `make rviz-sim` when the target publishes `/clock`; hardware defaults to
wall time. Other GUI tools accept their usual ROS arguments separately.

## Choose the ROS graph

```bash
make shell ROS_DOMAIN_ID=12
make rviz ROS_DOMAIN_ID=12 USE_SIM_TIME=false
# Optional explicit peers; keep the semicolon-separated value quoted:
ROS_DOMAIN_ID=12 ROS_STATIC_PEERS='192.168.1.20;192.168.1.21' \
    make shell
```

The image uses Fast DDS with explicit UDP transport and host networking. It does
not share host IPC. A controlled test found that a root publisher using shared
memory delivered no data to a host-user subscriber, while a same-user trial
passed. UDP avoids that permissions mismatch without running tools as root.
The smoke test verifies full-size camera delivery from a root peer that offers
both shared memory and UDP. The image uses the same ROS base digest as the
Simulation Adapter but builds independently, without depending on that image or
its configuration. Set the same domain as your target. Discovery defaults to
`SUBNET`; `ROS_AUTOMATIC_DISCOVERY_RANGE` and `ROS_STATIC_PEERS` are forwarded.
The target must also allow discovery and data transport. Host networking alone
does not solve multicast filtering, firewalls, routed networks, or VPN discovery.
Keep the default `SUBNET` setting for this UDP profile: `LOCALHOST` discovery did
not deliver data in the local validation trial. Use a distinct `ROS_DOMAIN_ID`
for local test graphs.

For another machine on the LAN, run Monitor on your workstation and connect to
the target's ROS graph. For a remote terminal, SSH into the Docker host, then run
`make -C Monitor shell` from the repository root. No SSH daemon runs inside the
image. Remote GUI forwarding and browser desktops are outside this initial setup.

Shell access has the normal ROS ability to publish and call services; this is not
a read-only security boundary. Host networking is intended for trusted tooling.

Standard ROS messages and `mavros_msgs` are installed. For custom messages, use a
compatible Jazzy workspace install tree (built without symlinks into absent source
or build directories):

```bash
MONITOR_OVERLAY_DIR=/absolute/path/to/install make shell
```

The tree is mounted read-only at `/overlay` and sourced automatically. Any extra
runtime libraries must also be installed in an extended image. Override
`MONITOR_IMAGE` to select that image; the `build` command builds the bundled
Dockerfile using the selected image tag.

## Record and inspect

`Monitor/logs/` is mounted at `/logs`, is writable by the host user, and is ignored
by Git. Other container files, including shell history, disappear on exit.

```bash
make shell
# Inside the container:
ros2 bag record -o /logs/camera-run --topics \
    /sensors/camera_0/color/image_raw /sensors/camera_0/depth/image_rect_raw \
    /sensors/camera_0/color/camera_info /tf /tf_static
# Stop recording with Ctrl-C, then inspect it:
ros2 bag info /logs/camera-run
```

Choose existing topic names with `ros2 topic list`. Record only the topics you
need, especially over a bandwidth-limited link. Saved RViz configurations can go
under `/logs` using File → Save Config As; reopen from the host with
`make rviz ARGS='-d /logs/my-view.rviz'` (or `make rviz-sim` for simulation time).

## Validate

Run the repository's existing static checks before building:

```bash
(cd ../Simulation && make validate)
make validate
make build
make smoke
```

The smoke test uses a root publisher and a host-user subscriber in independent
containers (matching the Adapter/tools UID split) to verify actual string,
1280x720 RGB/depth payload, and TF delivery. It creates no boat connection and
cleans up only its own test containers. It uses subnet discovery on domain 97;
set `MONITOR_TEST_DOMAIN_ID` to another unused domain if necessary. The publisher
offers UDP and 32 MiB shared memory; the tools container uses UDP. For diagnostic
comparisons, `MONITOR_TEST_PUBLISHER_USER` overrides the publisher UID:GID.
This proves
local container transport, not remote-LAN or hardware connectivity.

For GUI acceptance, open RViz on your desktop, check the fixed frame and live TF,
select a camera topic, and verify displayed frames arrive. With simulation
running, use `USE_SIM_TIME=true`; inspect a received image rather than relying on
topic discovery alone. No changes to the simulator are required.

If topics are missing, check domain, discovery scope, and target/network settings.
If names appear but data does not, inspect publisher QoS with `topic info
--verbose`, use matching QoS, and check UDP delivery and target transport settings.
For sensor CLI inspection, `ros2 topic echo TOPIC --qos-reliability best_effort`
can match best-effort publishers. For blank RViz, check the fixed frame, TF,
display topic/QoS, and simulation clock setting.

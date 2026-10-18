# One-time setup

## Supported host

This project targets a native Ubuntu Linux desktop. It uses Docker host
networking, the host X11/Xwayland display socket, and optional direct-rendering
devices. Docker Desktop on macOS or Windows is not supported by this V1.

The tested host target is Ubuntu 24.04 with Docker Engine and Docker Compose.
Gazebo and ArduPilot themselves are installed inside the Ubuntu 22.04 image.

## 1. Verify Docker access

Run:

```bash
docker info
docker compose version
```

Both commands must succeed without `sudo`. If Docker reports permission denied,
add your account to the `docker` group and then log out and back in:

```bash
sudo usermod -aG docker "$USER"
```

Do not enter a password into a chat or save it in this project.

## 2. Install the small host dependencies

```bash
sudo apt update
sudo apt install make xauth
```

No host ROS or Gazebo installation is required.

## 3. Make QGroundControl executable

```bash
chmod +x /home/ppatel/Applications/QGroundControl-v5.1.4-x86_64.AppImage
```

Launch it normally from the desktop or terminal. QGroundControl should
automatically discover the simulated boat on UDP port `14550`.

## 4. Validate and build

From the project root:

```bash
make validate
make build
```

The first build compiles ArduPilot Rover, the official ArduPilot Gazebo bridge,
and ASV Wave Sim. It requires network access and may take several minutes.

## Display and GPU notes

Run `make run` from the logged-in graphical desktop session so `$DISPLAY` and
its Xauthority cookie are available. The launcher creates a temporary
container-only Xauthority file; it does not use the insecure `xhost +` command.

The launcher probes NVIDIA container support and automatically uses a working
discrete GPU, including PRIME offload on hybrid laptops. Otherwise it uses Mesa
through `/dev/dri`. A missing NVIDIA runtime is reported rather than treated as
working graphics. See [performance setup](PERFORMANCE.md) for the Toolkit repair
helper, renderer verification and capture-rate settings. If direct rendering
fails, explicitly use CPU rendering:

```bash
SOFTWARE_RENDERING=1 make run
```
# Optional ROS 2 RGB-D setup

ROS 2 is containerized; do not install ROS or MAVROS on the host. Build the
simulator, adapter, and autonomy images with:

```bash
make ros-build
```

The Adapter image at `Adapter/simulation/` installs ROS 2 Jazzy, `ros_gz_bridge`,
MAVROS, and GeographicLib datasets. The separate evaluation image installs
OpenCV's ArUco module and MAVROS message types for explicit simulation-only
smoke tests. The autonomy image has none of those environment-facing runtime
dependencies.
Use `ADAPTER_IMAGE` and `AUTONOMY_IMAGE` to override their image names; the former
combined `ROS_IMAGE` setting is no longer used.
The build needs internet access and several additional gigabytes of Docker
storage. Verify available storage with `docker system df` and `df -h` before a
clean rebuild. Do not remove unrelated Docker data to make room.

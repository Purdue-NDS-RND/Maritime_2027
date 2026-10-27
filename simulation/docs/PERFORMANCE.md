# Simulation performance

The real-time factor is simulated seconds divided by elapsed real seconds.
At 0.28, ten simulated seconds take about 36 real seconds.

The launcher defaults to `SIM_GPU=auto`. On NVIDIA hosts it exercises the
container runtime before selecting discrete graphics, including PRIME offload
for both Gazebo's GUI and camera renderer. A stale Docker runtime registration
does not count as a working GPU. Failed automatic probes report the actual
error and use Mesa; `SIM_GPU=nvidia` fails instead of silently using another GPU.
Use `SIM_GPU=mesa` to compare integrated graphics. `SOFTWARE_RENDERING=1`
explicitly selects CPU rendering.

RGB-D capture defaults to **15 Hz in simulation time**, at the original
1280 x 720 resolution and calibration. At 0.28 real time, the previous 30 Hz
configuration delivered about 8.4 frames per real second while repeatedly
rendering frames that delayed simulation. `CAMERA_FPS=30` restores that capture
cadence when needed; valid overrides are 8..60 Hz. Each run creates a model
copy under `logs/generated-models/<run-id>/`, changing only camera update rates.
The image's verified model and authored payloads remain intact. The chosen
cadence is recorded in the Compose snapshot and `last-run.txt`.

```bash
SIM_GPU=nvidia BOAT_MODEL=dual SCENARIO=gate WATER=calm make run
```

The NVIDIA driver on the host and NVIDIA Container Toolkit for Docker are both
required. Follow the [official Toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
An OS upgrade may disable its apt source while leaving `nvidia` registered in
Docker. If startup reports `nvidia-container-runtime: executable file not found`,
restore the stable official repository and reinstall `nvidia-container-toolkit`.
The repository includes a repair helper using those official stable packages:

```bash
bash scripts/install-nvidia-container-toolkit.sh
```

It requires your sudo password and does not restart Docker or change its config.
If the runtime is not registered, the official configuration command is
`sudo nvidia-ctk runtime configure --runtime=docker`; restarting Docker affects
other running containers, so schedule that separately.

Confirm the actual renderer after startup:

```bash
docker exec ardupilot-blueboat-sim glxinfo -B
nvidia-smi
```

Look for an NVIDIA OpenGL renderer and Gazebo GPU processes, not merely
`direct rendering: Yes` (Intel Mesa can also report that). The configuration
preserves camera resolution, calibration, physics step size, and boat dynamics.

References: [Gazebo hybrid GPU guidance](https://gazebosim.org/docs/harmonic/troubleshooting/#problems-with-dual-intel-and-nvidia-gpu-systems),
[NVIDIA graphics and display capabilities](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html#driver-capabilities).


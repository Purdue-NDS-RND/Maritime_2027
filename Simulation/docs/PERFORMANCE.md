# Simulation performance

The real-time factor is simulated seconds divided by elapsed real seconds.
At 0.28, ten simulated seconds take about 36 real seconds.

Measure a fixed 20-second wall-time window, including pauses and delivery gaps:

```bash
make performance
make performance ARGS='--duration 30 --min-rtf 0.8'
make performance ARGS='--duration 60 --min-rtf 0.8 --navigation'
```

The last two commands fail below 80% real time. `--navigation` also records
mission stages and stop reasons and requires at least one ready navigation sample.
Compare identical boat, water,
camera and monitoring configurations; measure both idle and active navigation.

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

Faster rendering also exposes receipt-clock scheduling jitter. Live alignment
defers monotonic slope outliers until a valid enclosing reference arrives; it
never extrapolates. Backward/reset references and gaps above two seconds still
latch a fault. Pose and map freshness watchdogs keep their existing thresholds.
`/monitor/mapping/clock` reports deferred references alongside converted/dropped
poses. This remains experimental receipt alignment with unmeasured arrival bias.

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

## Shared-memory recovery

After many interrupted or forced-stop ROS runs, Fast DDS can leave unused shared
memory segments behind. If camera delivery falls while source rendering stays
fast, inspect `/dev/shm` from a host-IPC container: the sandbox's own `/dev/shm`
can show different contents. During regression testing this host filled its
16 GiB shared-memory filesystem, causing explicit SHM allocation errors and
synchronized delivery below the unchanged 8 Hz acceptance requirement.

Stop the simulation, then run `make dds-clean`. It uses the official
[Fast DDS cleaner](https://fast-dds.docs.eprosima.com/en/2.x/fastddscli/cli/cli.html)
to free unused DDS segments and respect segments still in use; it does not
delete arbitrary `/dev/shm` files. The measured cleanup removed 470 unused
segments and reduced usage from 100% to 1%. Restart ROS participants afterward
so they can establish working shared-memory transport again.

## Measured on 2026-10-18

Core Ultra 9 185H, RTX 4050 Laptop GPU, dual-camera gate, calm water, GUI on.
Idle means Gazebo/SITL and the Adapter. Full navigation additionally runs both
RGB detectors, shared mapper, Nav2, clock adapter, command bridge, truth-only
evaluator and `rviz-nav`. These are fixed clock-delta measurements, not the
Gazebo UI's instantaneous statistic.

| Configuration | Wall observation | Real-time factor |
| --- | --- | --- |
| Intel Mesa, 30 Hz cameras, idle | 20 s | 0.479 |
| NVIDIA, 30 Hz cameras, idle | 20 s | 0.558 |
| NVIDIA, 15 Hz cameras, idle | 20 s | 0.908 |
| NVIDIA, 15 Hz cameras, full navigation and RViz | 60 s | 0.875 |

Evidence: `logs/performance-mesa-idle.log`, `performance-nvidia-idle.log`,
`performance-nvidia-15-idle.log`, and `performance-final-full-stack.log`.
The full-stack capture includes bootstrap and gate following, with no stale-map
or stale-odometry stop reason. Conservative collision checks still stopped
commands when a predicted sweep was blocked.

Run `logs/navigation-20261018-123956/result.json` passed the entire gate in
110 s wall time, with 0.25 m minimum hull clearance from the conservative buoy
envelopes and 0.67 m whole-stern exit clearance. HOLD/disarm was verified.
The separate dual-camera check passed exact synchronization, 1280 x 720
dimensions, calibration, depth encoding, mount TF and visible marker checks.

The host's NVIDIA runtime entry existed but its executable was absent; its apt
source had been disabled with a `.distUpgrade` suffix. The official stable
Toolkit packages were restored at version 1.20.1 without restarting Docker.
The renderer was verified as NVIDIA in both `glxinfo` and Gazebo's Ogre log.
An experimental static-water change made the measured run slower and was
reverted; water settings and wave plugins are unchanged.

## Validation

`make validate` passed, including model preservation (4 tests), GPU selection
(4 tests), and camera cadence overrides (2 tests). Monitor validation and all
12 live mapping/clock tests passed. The dual-camera gate and synchronized
dual-camera sensor checks above were separate live runs.

After the shared-memory cleanup, `make verify-rgbd` passed all five scene
layouts (`one`, `gate`, `multi`, `repeated_red`, `slalom`), RGB-D source/public
checks, the Adapter boundary, MAVROS motion/stop/HOLD/disarm, and original
ArduPilot travel/stop/RTL/disarm. The repeated-color scene recovered from
6.79 Hz before cleanup to 15.00 Hz afterward, with the 8 Hz requirement intact.
See `logs/performance-verify-rgbd-clean.log` and `performance-shm-clean.log`.
The earlier suite was interrupted by lost host networking during a desk move;
the subsequent delivery failure and its repair are recorded separately.

`make lifecycle-smoke ARGS='--cases default_adapter,signal_int'` passed both
focused launcher checks: default Adapter ownership and SIGINT exit 130 with
all required containers removed. See `logs/performance-lifecycle.log`.
The documented `make dds-clean` target also passed after the suite.

Full-load recording was not tested by this performance change.

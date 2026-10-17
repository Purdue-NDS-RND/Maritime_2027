# Deployment Configuration

- `../Simulation/container/compose.yaml` owns SITL, the Simulation Adapter
  (including MAVROS and FCU transport), and explicitly invoked evaluators.
- `compose.base.yaml` retains the legacy opt-in bootstrap definition for
  development; Simulation does not include or launch it.

Run `make run` in `Simulation/` to start the simulator and Adapter. Start
navigation separately with `make run` in `autonomy/`; see
[gate and slalom navigation](../docs/GATE_SLALOM_NAVIGATION.md).
`ROS_SIM=0` is an explicit bare-SITL opt-out for direct-world operation.

All ROS services must use the same `ROS_DOMAIN_ID`. The current deployment uses
Linux host networking and preserves MAVLink ports 14550, 14551, and 14552. Container
separation does not enforce topic access security: ground truth is separated by
topic contract, and autonomy must not subscribe to it.

The Adapter and evaluation Compose services also use `ipc: host`. Fast DDS detects the shared
network host and may select shared-memory transport; separate container IPC
namespaces can otherwise allow discovery without delivery. This intentionally
reduces IPC isolation; do not use this deployment for untrusted workloads.
See the [Fast DDS Docker guidance](https://fast-dds.docs.eprosima.com/en/3.5.x/docker/shm_docker.html).
`make boundary-smoke` runs from the explicit simulation-only evaluation image.

GCS deployment and Jetson/ZED hardware-specific overrides remain future work.

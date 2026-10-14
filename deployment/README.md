# Deployment Configuration

- `compose.base.yaml` defines the reusable autonomy-bootstrap service; it is a
  fragment for the Simulation Compose file, not a standalone launch entry point.
- `../Simulation/container/compose.yaml` adds SITL, the Simulation Adapter
  (including MAVROS and FCU transport), the bootstrap, and explicit evaluators.

Use `Simulation/` Make targets for simulated operation; they handle scenarios,
display authorization, images, and shutdown. Plain `make run` still starts only
the simulator. `ROS_SIM=1` or `SCENARIO=...` adds the Simulation Adapter and bootstrap together.

All ROS services must use the same `ROS_DOMAIN_ID`. The current deployment uses
Linux host networking and preserves MAVLink ports 14550, 14551, and 14552. Container
separation does not enforce topic access security: ground truth is separated by
topic contract, and autonomy must not subscribe to it.

Both trusted ROS containers also use `ipc: host`. Fast DDS detects the shared
network host and may select shared-memory transport; separate container IPC
namespaces can otherwise allow discovery without delivery. This intentionally
reduces IPC isolation; do not use this deployment for untrusted workloads.
See the [Fast DDS Docker guidance](https://fast-dds.docs.eprosima.com/en/3.5.x/docker/shm_docker.html).
`make boundary-smoke` runs from the explicit simulation-only evaluation image.

GCS deployment and Jetson/ZED hardware-specific overrides remain future work.

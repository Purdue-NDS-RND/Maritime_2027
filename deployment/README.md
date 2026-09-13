# Deployment Configuration

- `compose.base.yaml` defines the reusable autonomy service; it is a fragment
  for `extends`, not the recommended launch entry point.
- `compose.autonomy.yaml` starts autonomy independently and requires `FCU_URL`.
- `../Simulation/container/compose.yaml` extends the same base and adds SITL connectivity,
  simulation, and the simulation-only adapter under its `ros` profile.

Use `Simulation/` Make targets for simulated operation; they handle scenarios,
display authorization, images, and shutdown. Plain `make run` still starts only
the simulator. `ROS_SIM=1` or `SCENARIO=...` adds adapter and autonomy together.

All ROS services must use the same `ROS_DOMAIN_ID`. The current deployment uses
Linux host networking and preserves MAVLink ports 14550, 14551, and 14552. Container
separation does not enforce topic access security: ground truth is separated by
topic contract, and autonomy must not subscribe to it.

Both trusted ROS containers also use `ipc: host`. Fast DDS detects the shared
network host and may select shared-memory transport; separate container IPC
namespaces can otherwise allow discovery without delivery. This intentionally
reduces IPC isolation; do not use this deployment for untrusted workloads.
See the [Fast DDS Docker guidance](https://fast-dds.docs.eprosima.com/en/3.5.x/docker/shm_docker.html).
`make boundary-smoke` checks actual data delivery from inside autonomy.

GCS deployment and Jetson/ZED hardware-specific overrides remain future work.

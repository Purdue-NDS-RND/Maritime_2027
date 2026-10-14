# Simulation Adapter

The active Simulation Adapter is `Adapter/simulation/`. It owns the
Gazebo-to-ROS bridges, normalized `camera_0` interfaces, MAVROS, FCU
connection/readiness diagnostics, and the SITL endpoint `udp://:14552@`.
It implements [MAVROS contract 2.0.0](../docs/contracts/mavros_adapter_contract.md)
and [camera contract 1.0.0](../docs/contracts/camera_adapter_contract.md).

It is not onboard autonomy and never launches evaluators. Explicit simulator
evaluators live in `Simulation/tests/evaluation/`; `make sensor-smoke`,
`make boundary-smoke`, and `make mavros-smoke` run them only after a simulation
profile is running. The command evaluator is guarded against physical devices.

The public camera interface is:

- `/sensors/camera_0/color/image_raw`
- `/sensors/camera_0/depth/image_rect_raw`
- `/sensors/camera_0/color/camera_info`
- `base_link -> camera_0_link -> camera_0_optical_frame`

Start through `Simulation/`:

```bash
make validate
SCENARIO=gate make run
make sensor-smoke
make boundary-smoke
make mavros-smoke
```

Adapter liveness is separate from camera source readiness and FCU readiness.
Perfect simulator pose stays on `/blueboat/ground_truth/...` for evaluation and
never enters shared autonomy navigation interfaces. Hardware Adapter work is
deferred; do not create or use `Adapter/hardware/` as a deployment option.

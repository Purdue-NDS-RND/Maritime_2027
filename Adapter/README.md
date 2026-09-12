# Simulation Adapter

This is simulation infrastructure, not onboard autonomy. It contains a small
ROS 2 workspace (`ros_ws/`) and its own image (`container/Dockerfile`).

It owns Gazebo-to-ROS bridges, simulated camera extrinsics, and evaluation-only
sensor/MAVROS smoke clients. MAVROS itself runs in the separate autonomy service.
The adapter needs `mavros_msgs` for its test client, but does not install or launch
the MAVROS server. Do not run the control smoke test against a physical vessel.

Start and test through the established workflow in `../Simulation/`:

```bash
make validate
make ros-build
SCENARIO=gate make run
# In another terminal in Simulation/:
make sensor-smoke
make boundary-smoke
make mavros-smoke
```

The image is `maritime-sim-adapter:jazzy` (override with `ADAPTER_IMAGE`). Both
sensor/MAVROS smoke commands execute here, exercising ROS interfaces across
containers. The read-only boundary test executes from autonomy via host-injected
test code and verifies camera reception and evaluation-only truth TF.
The adapter health check checks clock and optional RGB data; the autonomy health
check independently checks the flight-controller connection.

Camera topics and calibration remain unchanged by the extraction. Perfect pose
TF and its supporting static transforms use `/blueboat/ground_truth/tf` and
`/blueboat/ground_truth/tf_static`; the sensor evaluator remaps its listener there.
The adapter publishes only camera extrinsics on shared `/tf_static`; MAVROS
separately publishes fixed coordinate-convention conversions. The current
`zed2i_*` identifiers describe the old generic simulated RGB-D setup, not the
planned physical ZED X Mini cameras.

See [simulation operations](../Simulation/docs/RGBD_AND_BUOY_SCENARIOS.md) and
the [HLD](../docs/High_Level_Design.md). Generated workspace directories are ignored.

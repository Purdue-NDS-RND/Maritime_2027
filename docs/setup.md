# Setup and intended runtimes

Only the retained Gazebo/SITL simulator is runnable. Follow
[simulator setup](../simulation/docs/SETUP.md), then from `simulation/`:

```bash
make validate
make run
# Another terminal, if control validation is wanted:
make smoke
make down
```

Simulation uses one application container. Boat, drone and GCS have README-only
scaffolds for future independent containerized applications. ROS 2 belongs within
future vehicle applications; multiple nodes may share their application container.
`shared/` is code/data, not a service. No adapters or ROS integration from the old
implementation are retained.

Both vehicles use a Jetson and Pixhawk. Firmware and host drivers stay outside
application containers; desktop and Jetson builds may differ. Networking, device
access, images and deployment commands will be designed later. Boat development
must accept manual routes without drone/GCS; drone mapping must be testable
against measured locations without the boat.

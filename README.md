# Maritime 2027

Maritime 2027 is developing an onboard autonomy system for detecting,
understanding, and navigating buoy-marked waterways with a competition
low-profile vessel.

## Project documentation

- [Project Overview](docs/Project_Overview.md) defines the mission, intended
  outcomes, assumptions, and scope.
- [High-Level Design](docs/High_Level_Design.md) defines the planned system
  responsibilities, information flow, deployment boundaries, and future
  project organization.

Project-wide mission, requirements, and architecture documentation belongs in
`docs/`.

## Current simulator

[`Simulation/`](Simulation/) is the current BlueBoat ArduPilot/Gazebo
simulation baseline. It includes repeatable buoy scenarios, selectable single/dual
RGB-D cameras, the Simulation Adapter, and MAVROS checks. Perception, mapping
and gate/slalom navigation live in [`autonomy/`](autonomy/README.md) and start
separately.

Run simulator commands from `Simulation/`:

```bash
make validate
make run
make smoke
```

For dual-camera navigation, start the two components in separate terminals:

```bash
make -C Simulation run SCENARIO=slalom BOAT_MODEL=dual WATER=calm
make -C autonomy run ARGS=--evaluate
```

See the [simulator README](Simulation/README.md) for setup, operation, testing,
and simulator-specific documentation.

## ROS 2 tools

[`Monitor/`](Monitor/README.md) provides an independent ROS 2 shell, RViz2,
graph/image inspection, and bag recording for simulation or hardware ROS graphs:

```bash
make -C Monitor shell
make -C Monitor rviz-sim
```

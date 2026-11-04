# Drone sensing and perception

The planned drone app detects water objects with a fixed Arducam IMX519,
geolocates observations in a fixed ENU frame using time-aligned position and
attitude, consolidates physical instances, and exports a map to the GCS.
WGS84 coordinates are derived at the export boundary. The operator reviews
positions and assigns colors/course roles before preparing the boat route.

Start with [LLM.md](LLM.md) for retained project context and
[TASKS.md](TASKS.md) for the ordered backlog and acceptance criteria.
Codex instructions are in [AGENTS.md](AGENTS.md); the authorized write branch is
`feature/cv-raycast`. [ROS 2 package research](../docs/ros2_geolocation_packages.md)
recommends evaluating IPM + tf2 for projection before rebuilding custom raycasting.
Detailed topics are linked from that index, including calibration/error
measurement, reusable CUASC code and the proposed JSON contract.

Target hardware is an Orin Nano 8GB, fixed Arducam and ordinary GNSS (no RTK), with a
desired survey height below 5 m above water. Exact hardware integration,
timing, mounts, water datum and usable operating envelope need measurement.

The future app is independently runnable/containerized and uses ROS 2.
Its Pixhawk controls the vehicle; firmware and host drivers stay outside
the application. Flight control and boat launch/recovery belong to their
respective owners. A direct boat-drone perception link is not initially required.

Status as of 2026-11-04: design/review documents only; no drone algorithms,
survey controller or communication protocol are implemented here yet.
Validate maps independently against measured object locations before claiming
physical accuracy or navigation readiness.

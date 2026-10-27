# Repository guidelines

`boat/` owns supplied GPS route execution, tasks, Pixhawk integration and status.
`drone/` owns surveys, object detection and geolocation. `gcs/` owns map review,
route generation, mission upload and monitoring. `shared/` is common code/data,
not a service. Object coordinates and route waypoints are different concepts.

This is a clean restart around the retained simulator. The four application/
shared directories are README-only scaffolds. Develop the high level design
with the user before implementing algorithms, ROS packages, networking or schemas.
Do not restore the old adapter, mapping, navigation or monitoring architecture.
Initial boat routes must be testable without drone/GCS, cameras, Nav2, onboard
buoy mapping or continuous replanning. Camera-free feasibility needs evaluation
against survey/GPS/tracking error, buoy movement and whole-hull clearance.

Future apps are independently containerized, with multiple ROS nodes permitted
inside a vehicle app container. Use ROS 2 inside vehicle applications. Vehicle-GCS
networking is undecided. Pixhawk firmware and host drivers remain outside app
containers. Jetson and desktop builds may differ.

Run simulator commands from `simulation/`: `make validate`, `make build`,
`make run`, `make smoke`, `make down`. Simulation is one Gazebo/SITL/MAVProxy
container. `make smoke` needs a running boat and exercises actual movement,
HOLD, RTL and disarm. `make sensor-smoke` checks Gazebo cameras when enabled;
`make buoy-tracking-smoke` checks the buoy plugin. Preserve relevant simulator
checks, but do not expand legacy integration validation for this restart.
Configuration parsing and container health alone are not control acceptance.

Preserve simulator source pins, dynamics, parameters, camera calibration assets,
executable bits and direct MAVLink ports unless a change explicitly targets them.
Run appropriate static checks for path/configuration changes. Keep runtime logs,
recordings, generated SDF/manifests, EEPROM and caches out of Git under
`simulation/logs/`. Project direction/setup lives in `docs/`; simulator usage in
`simulation/docs/`.

Preserve uncommitted work and local data. Git history is the archive; do not
create an old implementation directory or modify `archive/pre-revamp`. Work on
`revamp`; do not force push, delete remote branches or merge this migration into
main. Use focused changes, four-space Python indentation, snake_case and strict
Bash entrypoints. PRs should explain runtime impact and actual validation limits.

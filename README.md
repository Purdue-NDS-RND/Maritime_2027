# Maritime 2027

A drone surveys the arena and estimates object GPS locations and types. The
ground station reviews that object map, prepares a predefined GPS route and
task instructions, and sends the mission to the boat. The boat executes the
supplied route through its Pixhawk and reports status.

Gate passage and slalom should initially work without camera input. This is a
capability to validate against survey error, GPS error, path tracking, buoy
movement, and hull clearance, not an established result. Task-specific cameras
may later support football toss or colored buoy contact.

| Directory | Responsibility |
| --- | --- |
| [boat/](boat/README.md) | GPS route execution, task coordination, Pixhawk integration, status |
| [drone/](drone/README.md) | Survey, object detection, geolocation |
| [gcs/](gcs/README.md) | Map review, route generation, mission upload, monitoring |
| [shared/](shared/README.md) | Future common code/data definitions; no service |
| [simulation/](simulation/README.md) | Retained Gazebo/SITL runtime, assets, tests |
| [docs/](docs/README.md) | Direction, migration notes, setup and hardware knowledge |

Boat, drone, and GCS are scaffolds only. No new mission implementation, message
schemas, networking, or detailed high level design is included. Each vehicle
has a Jetson for application processing and a Pixhawk for control. ROS 2 is used
within vehicle applications; the vehicle-to-GCS protocol is undecided.

Start with [the migration plan](docs/migration_plan.md) and
[setup instructions](docs/setup.md). The existing simulator can be run with
`make -C simulation run`; it does not yet implement the new boat application.

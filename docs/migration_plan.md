# Migration plan

## System direction

The drone surveys the arena and sends estimated object GPS locations and types
to the GCS. The GCS reviews the object map, prepares a predefined GPS route and
task instructions, and sends that mission to the boat. Both vehicles report
status to the GCS; no initial direct boat-to-drone connection is required.

Object maps say where objects are; route waypoints say where the boat should
travel. Task instructions describe mission actions. Keep these concepts separate.
Their formats, associations and network transport await design.

The boat Jetson coordinates route/task execution using its Pixhawk for vehicle
control. The drone also has a Jetson and Pixhawk. Initial gate/slalom execution
should need no camera, onboard buoy map, Nav2 or continuous replanning. Optional
perception can later support football toss or colored buoy contact.

## Runtimes and development order

Boat, drone, GCS and simulation are independent application areas. Future apps
are containerized; multiple ROS nodes may share each vehicle application
container. Use ROS 2 inside vehicle apps. `shared/` is common code/data, not a
service. Pixhawk firmware and host drivers stay outside application containers;
desktop and Jetson builds may differ. Vehicle-GCS protocol remains undecided.

1. Run the boat in simulation with a manually supplied GPS route.
2. Execute a predefined gate/slalom route without camera input.
3. Evaluate survey error, GPS error, tracking error, buoy movement and whole-hull
   clearance, including the stern. Camera-free feasibility remains unproven.
4. Verify route execution on the real boat.
5. Develop drone mapping independently against measured object locations.
6. Add GCS map review, route generation and mission upload.
7. Integrate the complete workflow.
8. Add task-specific perception where needed.

## What changed

The migration is a restart around the simulator. `boat/`, `drone/`, `gcs/` and
`shared/` contain only short READMEs. No replacement application logic, schemas,
ROS packages, networking, Dockerfiles for future apps, or detailed HLD was added.

- Renamed `Simulation/` to `simulation/` and updated launch/build paths.
- Retained Gazebo worlds, BlueBoat/camera/buoy assets, plugins, scenarios, SITL
  parameters, source pins and license declarations, GPU/display setup, direct
  MAVLink controls and relevant simulator-only tests.
- Removed the adapter entirely, including ROS bridges, MAVROS, camera-interface
  normalization, diagnostics, DDS configuration and integration/evaluation images.
  Simulation now has one Compose service for Gazebo/SITL/MAVProxy. The two direct
  MAVLink outputs remain; the adapter's unused third output was removed.
- Removed autonomy, perception, bearing EKF/occupancy mapping, Nav2, mission
  discovery/control, custom messages, Monitor, deployment bootstrap, mapping
  benchmarks, ROS recording/replay tools and tests specific to that design.
  The Nav2 lattice and accompanying license were removed together.
- Removed old architecture/contracts and implementation verification reports.
  Retained useful simulator setup knowledge and extracted the few historical
  hardware notes; no physical-camera calibration was found in removed sources.
- Existing ignored simulator data moved with `simulation/logs/`; Monitor output
  moved to `simulation/logs/pre-revamp-monitor/`. Recordings and local editor
  settings remain. Generated launcher/test logs may be refreshed by validation.

Work began on existing `revamp` at
`b1851a097f9715c9b0362cc2d3449f9ea681e33b`. The local `archive/pre-revamp`
branch was verified at that same commit and left unchanged. The initial tracked
worktree was clean with no nonignored untracked files. No new backup, main merge,
push or remote branch deletion was performed. Git history is the archive.

## Decisions for the upcoming design discussion

- Coordinate/datum conventions, map uncertainty, GPS hardware/corrections and
  acceptable error/clearance budgets.
- Route/task semantics, mission acceptance, progress and completion.
- Pixhawk integration, command ownership, override and failure behavior.
- Vehicle-GCS protocol, connectivity assumptions and upload acknowledgement.
- Drone survey/geolocation and independent measurement method.
- GCS operator workflow, hardware/build targets and later task-specific cameras.

See [validation](validation.md) for checks and limits. The existing simulator is
accepted as the starting baseline; extensive legacy integration testing is not
part of this restart.

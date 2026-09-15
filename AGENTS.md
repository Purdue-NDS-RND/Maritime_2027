# Repository Guidelines

## Project Structure & Module Organization

`Simulation/` contains the BlueBoat ArduPilot/Gazebo simulator. Treat it
as the active project root when running its commands. Key areas are
`config/` for SITL parameters, `worlds/` for Gazebo worlds, `models/` for
vehicle and buoy assets, and `scenarios/` for editable JSON layouts.
`Adapter/simulation/ros_ws/` owns simulation-only ROS bridges, camera frames,
MAVROS, and Adapter diagnostics. `Simulation/tests/evaluation/` owns explicit
simulation-only evaluators. `autonomy/ros_ws/` contains only the temporary
simulation bootstrap and must not depend on Gazebo, simulation truth, MAVROS,
or FCU transport. `deployment/` holds shared service
configuration. Runtime output
belongs in `logs/`; do not commit generated logs, rendered scenario files, or
Python cache files. Project-wide mission, requirements, and architecture
documentation lives in `docs/`. Simulator setup, operation, troubleshooting,
and maintenance documentation lives in `Simulation/docs/`.

## Build, Test, and Development Commands

Run commands from `Simulation/`:

```bash
make validate       # check scripts, assets, pinned sources, and Compose config
make build          # build/update the simulator image
make run            # start the GUI simulator
make smoke          # acceptance test of a running boat via MAVLink
make verify-rgbd    # complete RGB-D scenario and control regression suite
make down           # stop containers while retaining logs and SITL state
```

Use `SCENARIO=gate make run` for RGB-D work. Run `make validate` before a
build and the relevant smoke test after changes. `make smoke` requires a
running simulator; `make sensor-smoke` and `make mavros-smoke` run the explicit
simulation-only evaluation image and require the running Simulation Adapter.

## Coding Style & Naming Conventions

Keep shell scripts POSIX-compatible where practical, use `set -euo pipefail`
when editing Bash entrypoints, and preserve executable bits on runnable
scripts. Python uses four-space indentation, `snake_case` functions and
modules, and focused command-line scripts. Name Gazebo assets descriptively
(`blueboat_harbor.sdf`) and scenario layouts with lowercase names such as
`gate.json`. Keep environment variables uppercase (`WORLD`, `BUOY_SEED`).

## Testing Guidelines

Validation is layered: static checks (`make validate`), simulator control
acceptance (`make smoke`), and RGB-D/MAVROS regressions when applicable.
Do not treat a healthy container alone as success—record the semantic test
result. Changes to models, scenarios, bridges, frames, or MAVROS must run
`make verify-rgbd`. Keep test helpers named by purpose, e.g.
`sensor_smoke.py` and `mavros_smoke.py`.

## Commits & Pull Requests

History currently contains only the initial import; use short imperative
subjects such as `Add harbor buoy scenario` or `Fix MAVROS readiness check`.
Keep commits scoped to one concern. Pull requests should explain the runtime
impact, list validation commands and results, link the relevant issue, and
include screenshots or logs for visual/simulation behavior changes. Do not
silently change pinned upstream revisions, boat dynamics, or MAVLink ports.

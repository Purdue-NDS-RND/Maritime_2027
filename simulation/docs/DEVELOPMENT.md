# Simulator maintenance

`make run` invokes `scripts/run.sh`, Docker Compose, then `container/start-sim.sh`.
The container runs Gazebo, Rover SITL and MAVProxy. Host launch code owns GPU
selection, display authorization, configuration snapshots, locking and cleanup.
The container owns Gazebo/SITL readiness and process cleanup. No ROS runtime or
application mission controller is included.

Keep the existing source revisions and model hashes pinned. The Dockerfile and
Compose arguments record ArduPilot, ardupilot_gazebo, SITL_Models and ASV Wave Sim
revisions. Preserve original hull dynamics and `config/blueboat.parm` unless a
separate change explicitly targets them. Camera payloads add no mass/collision.

Scenario JSON and authored models are source. Generated SDF/manifests, run
snapshots and EEPROM belong in ignored `logs/`. `WIPE_PARAMS=1` explicitly resets
virtual EEPROM; ordinary shutdown retains it. Existing recordings remain local.

Run `make validate` for syntax, protected hashes, source pins, scenario/model
structure, Compose and available Gazebo SDF checks. Pure simulator tests run with
`python3 -m unittest discover -s tests -p 'test_*.py' -q`. `make smoke` tests actual
movement, HOLD, RTL and disarm on a running boat. `make sensor-smoke` checks
Gazebo camera output; `make buoy-tracking-smoke` checks the buoy plugin.
Configuration parsing and container health alone do not prove control behavior.

MAVProxy outputs remain UDP 14550 for host QGroundControl and 14551 for program
control/tests. Use only one controller on the program endpoint at a time.

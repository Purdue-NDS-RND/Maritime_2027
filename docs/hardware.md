# Hardware knowledge

Both vehicles will have a Jetson for application processing and a Pixhawk for
control. The test boat runs ArduPilot and already supports GPS waypoint missions.
Exact hardware models, firmware versions, drone firmware, GPS/corrections,
physical transport and driver versions remain to be confirmed. Firmware and host
drivers stay outside apps.

The old plan mentioned a boat Jetson Orin Nano and two ZED X Mini cameras with
a capture card and MIPI cables. These were planning notes, not verified hardware
or prerequisites for GPS route execution. No measured physical-camera calibration,
camera serial assignments or hardware FCU URL was found in the removed code.

`simulation/config/blueboat.parm` preserves SITL parameters. Camera payloads in
`simulation/models/` preserve simulated optics/mounts. Source dependency pins
remain in the simulator Dockerfile and Compose file. The simulator exposes
MAVLink on UDP 14550 (ground station) and 14551 (boat app/program/tests). The web
GCS now consumes 14550 by default; other ground stations need a separate
forwarded output. Its telemetry connection, serial baud and autopilot IDs are
configurable for future radio use such as an RFD900, either through a host
forwarder or direct device access. No physical radio/device configuration has
been verified. This does not choose mission delivery to the onboard application.

The approximate BlueBoat dynamics are not calibrated competition-boat dynamics.

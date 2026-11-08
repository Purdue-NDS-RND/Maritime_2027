# Hardware knowledge

## Current sensing/perception direction, 2026-11-08

The user plans an Orin Nano 8GB on each vehicle and a fixed 16 MP Arducam IMX519
with M12 wide-angle lens on the drone, with survey flight ideally below 5 m above water.
Ordinary GNSS replaced RTK by user instruction on 2026-11-04; no RTK base/correction
link is a deployment requirement. The selected camera is the
[IMX519 M12 module](https://www.uctronics.com/16mp-imx519-camera-module-with-m12-lens-wide-angle-color-rolling-shutter-for-raspberry-pi-and-openhd.html).
These are stated plans, not verified installed hardware or accuracy evidence.
Record lens/focus, sensor mode, carrier/JetPack, autopilot, GNSS receiver,
attitude source, clock behavior, antenna/camera lever arms and
water elevation before geolocation acceptance. CPU/GPU share the Jetson memory.

The CUASC 3840x2160 ROS/Kalibr intrinsic files are now packaged as historical
candidates with source commit/blob provenance. They do not certify this M12 lens,
focus, new resolution/mode, camera mount or timing. Configurable Argus capture and
recording/ROS publication are implemented; see [capture setup](../drone/README.md#arducam-imx519-image-capture).
Physical camera/Jetson, driver compatibility, exposure/gain achievement and rolling-shutter
timing remain untested. A matching Python >=3.11/GI/ROS runtime must be selected before
using the retained processing dependency pins on the actual Jetson.

The user describes two ZED Mini cameras for later boat mission perception;
the historical notes below describe ZED X Mini. Confirm exact SKU/serials,
interfaces and two-camera support before choosing capture hardware/drivers.
See [sensing architecture](sensing_perception.md) and
[geolocation](geolocation.md) for required measurements.

## Retained baseline knowledge

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

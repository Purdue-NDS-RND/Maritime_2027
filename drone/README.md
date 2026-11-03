# Drone

Future independently runnable, containerized Jetson application using ROS 2
for survey coordination, object detection, and geolocation. Its Pixhawk controls
the vehicle; firmware and host hardware drivers stay outside the application.

Send estimated object GPS locations and types to the GCS and report status.
Test generated maps independently against measured object locations. No direct
boat connection is initially required. No algorithms, survey controller, or
communication protocol are implemented here yet.

The GCS file-import boundary accepts `{"points": [...]}` with one consolidated
GPS position per object. Each row needs `latitude` and `longitude`; `id`, `color`
and `object_type` are optional. Use `"object_type": "unknown"` for an
unclassified object; omitted types also become unknown. No radius, height or
route is required. The GCS applies operator-selected hard/soft distances directly
from these GPS points and requires task-assignment review. See the
[GCS import guide](../gcs/README.md#gps-assisted-planner) for examples and limits.

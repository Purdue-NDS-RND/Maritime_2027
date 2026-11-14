# Drone sensing and perception

Implemented on `feature/cv-raycast`: a source-independent pixel/state -> ENU observation
-> correlated uncertainty -> physical-instance tracking -> WGS84 JSON pipeline, with
seeded synthetic survey generation, withheld evaluation and deterministic recording/replay.
The default tracker is static/random-walk. No constant-velocity or moving-object claim
is made. The supplied hardware bag demonstrates camera/FCU topic flow on the user's
Jetson/ROS host. Trained detection, full raw-source normalization, Docker deployment,
sustained onboard performance and physical accuracy remain unvalidated. The IMU recorder feeds the processing/replay
boundary when paired with verified same-time navigation. Existing GCS import and boat
behavior are unchanged.

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

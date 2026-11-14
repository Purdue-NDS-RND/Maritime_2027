# Shared library

`geometry.py` implements the small-course geographic projection and planar
geometry. Gazebo +X is east, +Y north for the pinned bridge. The projection
matches ArduPilot's mean-latitude longitude scaling; it is intentionally
restricted to local courses away from the poles.

`clearance.py` checks finite route segments (including the start connection),
ordered orientation-independent passages and finish regions using a point route and an
operator-selected total clearance buffer. The buffer is the distance from the
boat reference point to each live object GPS centre. No object radius is
added; the configured hard distance includes object size, hull and error allowances.
Native simulator/legacy maps retain physical surface geometry for compatibility. There are no hull identities, measured
navigation profiles, gain requirements or hidden margins. Speed must be finite
and positive; validation does not predict speed-dependent tracking or turns.

This directory is a library, not a service. It has no ROS, MAVLink or vehicle
control dependencies. Independent runtime acceptance uses the simulator's
oriented footprint recorder/evaluator rather than this static buffer check.

`object_map.py` validates buoy-only version 1 maps and version 2 maps with
circle/convex-polygon obstacles, nonblocking station annotations and start poses.
Route segments and the whole finish region are checked against every physical
object; deployment overlays do not add obstacles.

`course.py` provides finite directed gate/turn progress and planning/channel
containment. Live version 3 maps support dimension-free `point` objects, need no simulator identity and are never
simulator verified. GCS backend planning lives in `gcs/app/planner.py`; shared
code contains geometry and final validation, not a planning/control service.
For a channel finish selected beyond its final buoy pair, that pair is the
actual final passage. Containment remains mandatory through the finite exit
crossing; only then may the route leave for its stopping region. The complete
route and stopping disk still obey global boundaries and obstacle buffers.
GPS channel task finishes before the final gate are invalid. Older tabs cannot
restore such a finish through workspace save; generation and final validation
also enforce the final crossing and stopping allowance.

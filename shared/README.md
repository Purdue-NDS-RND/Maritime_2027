# Shared library

`geometry.py` implements the small-course geographic projection and planar
geometry. Gazebo +X is east, +Y north for the pinned bridge. The projection
matches ArduPilot's mean-latitude longitude scaling; it is intentionally
restricted to local courses away from the poles.

`clearance.py` checks finite route segments (including the start connection),
ordered fixed-course passages and finish regions using a point route and an
operator-selected total clearance buffer. The buffer is the distance from the
boat reference point to each physical obstacle surface. There are no hull identities, measured
navigation profiles, gain requirements or hidden margins. Speed must be finite
and positive; validation does not predict speed-dependent tracking or turns.

This directory is a library, not a service. It has no ROS, MAVLink or vehicle
control dependencies. Independent runtime acceptance uses the simulator's
oriented footprint recorder/evaluator rather than this static buffer check.

`object_map.py` validates buoy-only version 1 maps and version 2 maps with
circle/convex-polygon obstacles, nonblocking station annotations and start poses.
Route segments and the whole finish region are checked against every physical
object; deployment overlays do not add obstacles.

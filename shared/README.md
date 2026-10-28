# Shared library

`geometry.py` implements the small-course geographic projection and planar
geometry. Gazebo +X is east, +Y north for the pinned bridge. The projection
matches ArduPilot's mean-latitude longitude scaling; it is intentionally
restricted to local courses away from the poles.

`clearance.py` checks finite route segments (including the start connection),
waypoint transitions, ordered fixed-course passages and finish regions using
an enclosing boat circle. The profile supplies measured speed/turn/spacing
limits and position/tracking error. Validation adds 0.10 m reserve and the
operator's clearance without silently altering the route.

This directory is a library, not a service. It has no ROS, MAVLink or vehicle
control dependencies. Independent runtime acceptance uses the simulator's
oriented footprint recorder/evaluator rather than this preflight circle.

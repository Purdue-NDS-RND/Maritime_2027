# Drone

Future independently runnable, containerized Jetson application using ROS 2
for survey coordination, object detection, and geolocation. Its Pixhawk controls
the vehicle; firmware and host hardware drivers stay outside the application.

Send estimated object GPS locations and types to the GCS and report status.
Test generated maps independently against measured object locations. No direct
boat connection is initially required. No algorithms, survey controller, or
communication protocol are implemented here yet.

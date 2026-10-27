# Boat

Future independently runnable, containerized application for manually supplied
GPS routes, task coordination, Pixhawk integration, and status reporting.
ROS 2 nodes may share this application container on the boat Jetson. Pixhawk
firmware and host drivers stay outside it; desktop and Jetson builds may differ.

The initial gate/slalom approach uses supplied GPS waypoints without camera
input, Nav2, onboard buoy mapping, or continuous replanning. Optional task
perception can be added later. This directory deliberately contains no runtime
implementation yet. Start development with manually supplied routes in simulation.

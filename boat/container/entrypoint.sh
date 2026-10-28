#!/usr/bin/env bash
set -Eeuo pipefail
# ROS-generated setup scripts access optional unset variables.
set +u
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
set -u
exec "$@"

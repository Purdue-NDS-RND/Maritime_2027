#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME"
# ROS setup scripts do not support nounset in every package.
set +u
source /opt/ros/jazzy/setup.bash
source /opt/monitor/interfaces_ws/install/setup.bash
if [[ -f /overlay/setup.bash ]]; then
    source /overlay/setup.bash
fi
set -u
exec "$@"

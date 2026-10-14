#!/usr/bin/env bash
set -Eeuo pipefail

pgrep -f '[g]z sim' >/dev/null
pgrep -f '[a]rdurover' >/dev/null
pgrep -f '[m]avproxy.py' >/dev/null

clock_topic=$(timeout 3 gz topic -l 2>/dev/null | sed -n '/^\/world\/.*\/clock$/p' | head -n 1)
[[ -n $clock_topic ]]
python3 /opt/boat_sim/scripts/gazebo_clock_ready.py "$clock_topic"

if [[ ${CAMERA_ENABLED:-0} == 1 ]]; then
    topics=$(timeout 3 gz topic -l 2>/dev/null)
    grep -q '^/blueboat/rgbd_camera/image$' <<<"$topics"
    grep -q '^/blueboat/rgbd_camera/depth_image$' <<<"$topics"
    grep -q '^/blueboat/rgbd_camera/camera_info$' <<<"$topics"
fi

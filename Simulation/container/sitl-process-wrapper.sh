#!/usr/bin/env bash
set -Eeuo pipefail

log_file=${SITL_PROCESS_LOG:?SITL_PROCESS_LOG must name the ArduRover log file}
exec "$@" >>"$log_file" 2>&1

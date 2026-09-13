#!/usr/bin/env bash
set -Eeuo pipefail

LOG_DIR=${LOG_DIR:-/sim}
STATE_DIR="$LOG_DIR/state"
WORLD=${WORLD:-blueboat_waves.sdf}
MAVLINK_QGC=${MAVLINK_QGC:-udp:127.0.0.1:14550}
MAVLINK_API=${MAVLINK_API:-udp:127.0.0.1:14551}
MAVLINK_MAVROS=${MAVLINK_MAVROS:-udp:127.0.0.1:14552}
ENABLE_MAVROS=${ENABLE_MAVROS:-0}
CAMERA_ENABLED=${CAMERA_ENABLED:-0}
GAZEBO_STARTUP_TIMEOUT=${GAZEBO_STARTUP_TIMEOUT:-90}
WIPE_PARAMS=${WIPE_PARAMS:-0}
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
GAZEBO_LOG="$LOG_DIR/gazebo-$RUN_ID.log"
SIM_VEHICLE_LOG="$LOG_DIR/sim-vehicle-$RUN_ID.log"
ARDUROVER_LOG="$LOG_DIR/ardurover-$RUN_ID.log"
MAVLINK_LOG="$LOG_DIR/mavlink-$RUN_ID.tlog"

mkdir -p "$LOG_DIR" "$STATE_DIR"
touch "$GAZEBO_LOG" "$SIM_VEHICLE_LOG" "$ARDUROVER_LOG" "$MAVLINK_LOG"
export XDG_RUNTIME_DIR="$STATE_DIR/runtime"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"

case "${SOFTWARE_RENDERING:-0}" in
    1|true|TRUE|yes|YES|on|ON) export LIBGL_ALWAYS_SOFTWARE=1 ;;
esac

export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ardupilot_gazebo/build:/opt/asv_wave_sim/install/lib${GZ_SIM_SYSTEM_PLUGIN_PATH:+:$GZ_SIM_SYSTEM_PLUGIN_PATH}
export GZ_SIM_RESOURCE_PATH=/sim/generated-worlds:/opt/boat_sim/worlds:/opt/boat_sim/models:/opt/SITL_Models/Gazebo/models:/opt/ardupilot_gazebo/models:/opt/ardupilot_gazebo/worlds:/opt/asv_wave_sim/gz-waves-models/models:/opt/asv_wave_sim/gz-waves-models/world_models:/opt/asv_wave_sim/gz-waves-models/worlds${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}

gazebo_pid=
sitl_pid=

stop_group() {
    local pid=${1:-}
    [[ -n $pid ]] || return 0
    if kill -0 "$pid" 2>/dev/null; then
        kill -TERM -- "-$pid" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.25
        done
        kill -KILL -- "-$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
}

cleanup() {
    local status=$?
    trap - EXIT INT TERM
    echo "Stopping ArduRover, MAVProxy, and Gazebo..."
    stop_group "$sitl_pid"
    stop_group "$gazebo_pid"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cat > "$LOG_DIR/last-run.txt" <<EOF
run_id=$RUN_ID
world=$WORLD
mavlink_qgc=$MAVLINK_QGC
mavlink_api=$MAVLINK_API
mavlink_mavros=$MAVLINK_MAVROS
enable_mavros=$ENABLE_MAVROS
camera_enabled=$CAMERA_ENABLED
software_rendering=${LIBGL_ALWAYS_SOFTWARE:-0}
gazebo_log=$(basename "$GAZEBO_LOG")
sim_vehicle_log=$(basename "$SIM_VEHICLE_LOG")
ardurover_log=$(basename "$ARDUROVER_LOG")
mavlink_log=$(basename "$MAVLINK_LOG")
EOF

echo "Starting Gazebo Harmonic world: $WORLD"
setsid gz sim -v4 -r "$WORLD" > >(tee -a "$GAZEBO_LOG") 2>&1 &
gazebo_pid=$!

echo "Waiting up to ${GAZEBO_STARTUP_TIMEOUT}s for advancing simulation time and BlueBoat topics..."
deadline=$((SECONDS + GAZEBO_STARTUP_TIMEOUT))
ready=0
while (( SECONDS < deadline )); do
    if ! kill -0 "$gazebo_pid" 2>/dev/null; then
        echo "ERROR: Gazebo exited during startup. See $GAZEBO_LOG" >&2
        exit 1
    fi
    topics=$(timeout 4 gz topic -l 2>/dev/null || true)
    clock_topic=$(sed -n '/^\/world\/.*\/clock$/p' <<<"$topics" | head -n 1)
    camera_ready=1
    if [[ $CAMERA_ENABLED == 1 ]] && ! grep -q '^/blueboat/rgbd_camera/depth_image$' <<<"$topics"; then
        camera_ready=0
    fi
    if [[ -n $clock_topic ]] && grep -q '^/model/blueboat/odometry$' <<<"$topics" && [[ $camera_ready == 1 ]]; then
        if timeout 4 gz topic -e -t "$clock_topic" -n 1 2>/dev/null | grep -q 'sim'; then
            ready=1
            break
        fi
    fi
    sleep 1
done
if [[ $ready -ne 1 ]]; then
    echo "ERROR: Gazebo did not publish advancing time and BlueBoat odometry within ${GAZEBO_STARTUP_TIMEOUT}s." >&2
    echo "See $GAZEBO_LOG" >&2
    exit 1
fi
echo "Gazebo time is advancing and BlueBoat is present."

sitl_args=(
    -v Rover
    -f rover-skid
    --model JSON
    --no-rebuild
    --no-extra-ports
    --use-dir "$STATE_DIR"
    --add-param-file=/opt/boat_sim/config/blueboat.parm
    --custom-location=51.566151,-4.034345,0.0,0
    --out "$MAVLINK_QGC"
    --out "$MAVLINK_API"
    --mavproxy-args "--non-interactive --logfile=$MAVLINK_LOG"
)
case "${ENABLE_MAVROS,,}" in
    1|true|yes|on) sitl_args+=(--out "$MAVLINK_MAVROS") ;;
    0|false|no|off|"") ;;
    *) echo "ERROR: ENABLE_MAVROS has invalid value: $ENABLE_MAVROS" >&2; exit 2 ;;
esac
case "${WIPE_PARAMS,,}" in
    1|true|yes|on) sitl_args+=(--wipe-eeprom) ;;
    0|false|no|off|"") ;;
    *) echo "ERROR: WIPE_PARAMS has invalid value: $WIPE_PARAMS" >&2; exit 2 ;;
esac

echo "Starting ArduPilot Rover SITL as a skid-steer boat."
if [[ ${ENABLE_MAVROS,,} =~ ^(1|true|yes|on)$ ]]; then
    echo "MAVLink outputs: $MAVLINK_QGC, $MAVLINK_API, and MAVROS $MAVLINK_MAVROS"
else
    echo "MAVLink outputs: $MAVLINK_QGC and $MAVLINK_API"
fi
cd /opt/ardupilot
export SITL_RITW_TERMINAL=/usr/local/bin/sitl-process-wrapper.sh
export SITL_PROCESS_LOG=$ARDUROVER_LOG
setsid sim_vehicle.py "${sitl_args[@]}" > >(tee -a "$SIM_VEHICLE_LOG") 2>&1 &
sitl_pid=$!

while true; do
    if ! kill -0 "$gazebo_pid" 2>/dev/null; then
        wait "$gazebo_pid" || true
        echo "ERROR: Gazebo stopped unexpectedly. See $GAZEBO_LOG" >&2
        exit 1
    fi
    if ! kill -0 "$sitl_pid" 2>/dev/null; then
        wait "$sitl_pid" || true
        echo "ERROR: sim_vehicle.py stopped unexpectedly. See $SIM_VEHICLE_LOG and $ARDUROVER_LOG" >&2
        exit 1
    fi
    sleep 1
done

#!/usr/bin/env bash
set -Eeuo pipefail

LOG_DIR=${LOG_DIR:-/sim}
STATE_DIR="$LOG_DIR/state"
WORLD=${WORLD:-blueboat_waves.sdf}
MAVLINK_QGC=${MAVLINK_QGC:-udp:127.0.0.1:14550}
MAVLINK_API=${MAVLINK_API:-udp:127.0.0.1:14551}
MAVLINK_STREAMRATE=${MAVLINK_STREAMRATE:-4}
case "$MAVLINK_STREAMRATE" in
    4|10|20) ;;
    *) echo "ERROR: MAVLINK_STREAMRATE must be 4, 10, or 20 Hz." >&2; exit 2 ;;
esac
CAMERA_ENABLED=${CAMERA_ENABLED:-0}
GAZEBO_STARTUP_TIMEOUT=${GAZEBO_STARTUP_TIMEOUT:-90}
WIPE_PARAMS=${WIPE_PARAMS:-0}
RUN_ID=${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}
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

if [[ $CAMERA_ENABLED == 1 ]]; then
    camera_model=blueboat_rgbd
    [[ ${BOAT_MODEL:-single} != dual ]] || camera_model=blueboat_dual_rgbd
    runtime_models="$LOG_DIR/generated-models/$RUN_ID"
    python3 /opt/boat_sim/scripts/configure_camera_rate.py \
        --source "/opt/boat_sim/models/$camera_model" \
        --output "$runtime_models/$camera_model" --rate "${CAMERA_FPS:-15}"
    export GZ_SIM_RESOURCE_PATH="$runtime_models:$GZ_SIM_RESOURCE_PATH"
fi

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
scenario=${SCENARIO:-none}
configuration_sha256=${RUN_CONFIG_SHA256:-unknown}
application_state=empty_simulation_placeholder
mavlink_qgc=$MAVLINK_QGC
mavlink_api=$MAVLINK_API
camera_enabled=$CAMERA_ENABLED
camera_fps=${CAMERA_FPS:-15}
software_rendering=${LIBGL_ALWAYS_SOFTWARE:-0}
gazebo_log=$(basename "$GAZEBO_LOG")
sim_vehicle_log=$(basename "$SIM_VEHICLE_LOG")
ardurover_log=$(basename "$ARDUROVER_LOG")
mavlink_log=$(basename "$MAVLINK_LOG")
EOF

# Resolve once, snapshot all model/mesh inputs, then launch only the snapshot.
scene_dir="$LOG_DIR/runs/$RUN_ID/scene"
world_source="$WORLD"
if [[ ! -f $world_source ]]; then
    for root in ${GZ_SIM_RESOURCE_PATH//:/ }; do
        if [[ -f $root/$WORLD ]]; then world_source="$root/$WORLD"; break; fi
    done
fi
python3 /opt/boat_sim/scripts/scene_snapshot.py "$scene_dir" --world "$world_source"
export GZ_SIM_RESOURCE_PATH="$scene_dir/models:$GZ_SIM_RESOURCE_PATH"
WORLD="$scene_dir/world.sdf"
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
    if [[ $CAMERA_ENABLED == 1 && ${BOAT_MODEL:-single} == dual ]] && ! grep -q '^/blueboat/camera_1/depth_image$' <<<"$topics"; then
        camera_ready=0
    fi
    if [[ -n $clock_topic ]] && grep -q '^/model/blueboat/odometry$' <<<"$topics" && [[ $camera_ready == 1 ]]; then
        if python3 /opt/boat_sim/scripts/gazebo_clock_ready.py "$clock_topic"; then
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

spawn_heading=0
[[ ${SCENARIO:-none} != competition ]] || spawn_heading=270
sitl_args=(
    -v Rover
    -f rover-skid
    --model JSON
    --no-rebuild
    --no-extra-ports
    --use-dir "$STATE_DIR"
    --add-param-file=/opt/boat_sim/config/blueboat.parm
    --custom-location=51.566151,-4.034345,0.0,$spawn_heading
    --out "$MAVLINK_QGC"
    --out "$MAVLINK_API"
    --mavproxy-args "--non-interactive --streamrate=$MAVLINK_STREAMRATE --logfile=$MAVLINK_LOG"
)
case "${WIPE_PARAMS,,}" in
    1|true|yes|on) sitl_args+=(--wipe-eeprom) ;;
    0|false|no|off|"") ;;
    *) echo "ERROR: WIPE_PARAMS has invalid value: $WIPE_PARAMS" >&2; exit 2 ;;
esac

echo "Starting ArduPilot Rover SITL as a skid-steer boat."
echo "MAVLink outputs: $MAVLINK_QGC and $MAVLINK_API"
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

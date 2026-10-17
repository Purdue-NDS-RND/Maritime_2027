#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_DIR"

build_mode=if-missing
action=up
interactive=1

usage() {
    cat <<'EOF'
Usage: make run|build|rebuild|down

Internal form: scripts/run.sh [--build|--build-only|--rebuild-only|--down|--non-interactive|--help]

  no option       Start the simulation, building the image if absent
  --build         Rebuild the image, then start the simulation
  --build-only    Build the image without starting the simulation
  --rebuild-only  Force a clean image rebuild without starting
  --down          Stop and remove this project's container
  --non-interactive Start with environment/defaults without the setup menu

In a terminal, starting without WORLD or SCENARIO opens a quick setup menu.
Explicit WORLD/SCENARIO selections and redirected input/output skip the menu.

Environment:
  SCENARIO=one|gate|multi|repeated_red|slalom  Launch an RGB-D buoy scenario with ROS
  BUOY_SEED=<integer>      Deterministically randomize the selected scenario
  BOAT_MODEL=single|dual   Select forward or -45/+45 degree camera boat; enables ROS
  WATER=calm|normal|harsh  Override water independently of the world/scenario
  ROS_SIM=1                Enable ROS/MAVROS for a direct WORLD launch
  STACK_STARTUP_TIMEOUT=180 Bounded readiness timeout per service (seconds)
EOF
}

case "${1:-}" in
    "") ;;
    --build) build_mode=always ;;
    --build-only) build_mode=always; action=build ;;
    --rebuild-only) build_mode=no-cache; action=build ;;
    --down) action=down ;;
    --non-interactive) interactive=0 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
esac

if [[ $action == up && $interactive == 1 && -t 0 && -t 1 && -z ${WORLD:-} && -z ${SCENARIO:-} ]]; then
    source "$PROJECT_DIR/scripts/run-menu.sh"
    configure_simulation
fi

if [[ $(uname -s) != Linux ]]; then
    echo "ERROR: this project requires native Linux for host networking and X11 forwarding." >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker Engine is not installed." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: the Docker Compose plugin is unavailable." >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    cat >&2 <<EOF
ERROR: Docker is installed but this user cannot reach the daemon.
Add ${USER:-your-user} to the docker group, then log out and back in:
  sudo usermod -aG docker "${USER:-your-user}"
EOF
    exit 1
fi

export HOST_UID=${HOST_UID:-$(id -u)}
export HOST_GID=${HOST_GID:-$(id -g)}
export VIDEO_GID=${VIDEO_GID:-$(getent group video | cut -d: -f3 || true)}
export RENDER_GID=${RENDER_GID:-$(getent group render | cut -d: -f3 || true)}
VIDEO_GID=${VIDEO_GID:-$HOST_GID}
RENDER_GID=${RENDER_GID:-$HOST_GID}
export VIDEO_GID RENDER_GID
export SIM_IMAGE=${SIM_IMAGE:-ardupilot-blueboat:4.7.0}
export ADAPTER_IMAGE=${ADAPTER_IMAGE:-maritime-sim-adapter:jazzy}
export AUTONOMY_IMAGE=${AUTONOMY_IMAGE:-maritime-autonomy:jazzy}
export EVALUATION_IMAGE=${EVALUATION_IMAGE:-maritime-sim-evaluation:jazzy}

compose_files=(-f container/compose.yaml)
if [[ -d /dev/dri ]]; then
    compose_files+=(-f container/compose.gpu.yaml)
fi
if [[ $action == down ]]; then
    docker compose "${compose_files[@]}" --profile ros --profile evaluation down --remove-orphans
    # Remove only the exact temporary credential file recorded by this project.
    if [[ -f logs/active-xauth.path ]]; then
        recorded_xauth=$(cat logs/active-xauth.path)
        case "$recorded_xauth" in
            /tmp/ardupilot-blueboat-xauth.*|/run/user/"$HOST_UID"/ardupilot-blueboat-xauth.*)
                rm -f -- "$recorded_xauth" ;;
        esac
        rm -f logs/active-xauth.path
    fi
    exit 0
fi

# A second launcher must not replace a live scenario or its display credentials.
# The lock also covers rendering/build preparation, which writes shared inputs.
# --down remains independent so it can stop an existing launcher.
mkdir -p logs
if ! command -v flock >/dev/null 2>&1; then
    echo "ERROR: flock is required to protect the simulation launch lifecycle." >&2
    exit 1
fi
exec 9>logs/.launcher.lock
if ! flock -n 9; then
    echo "ERROR: another simulation launcher owns this project; use make down before starting a new run." >&2
    exit 1
fi
for existing_container in ardupilot-blueboat-sim maritime-sim-adapter maritime-autonomy; do
    if docker container inspect "$existing_container" >/dev/null 2>&1; then
        echo "ERROR: existing project container $existing_container would be replaced; use make down first." >&2
        exit 1
    fi
done

case "${BOAT_MODEL:-single}" in
    single|dual) ;;
    *) echo 'ERROR: BOAT_MODEL must be single or dual.' >&2; exit 2 ;;
esac
if [[ -n ${BOAT_MODEL:-} ]]; then
    export ROS_SIM=1 CAMERA_ENABLED=1
fi
scenario=${SCENARIO:-}
case "${WATER:-}" in
    ''|calm|normal|harsh) ;;
    *) echo 'ERROR: WATER must be calm, normal, or harsh.' >&2; exit 2 ;;
esac
if [[ -n $scenario && -n ${WORLD:-} ]]; then
    echo "ERROR: SCENARIO and WORLD are mutually exclusive." >&2
    exit 2
fi
if [[ -n ${BUOY_SEED:-} && ! ${BUOY_SEED} =~ ^-?[0-9]+$ ]]; then
    echo "ERROR: BUOY_SEED must be an integer." >&2
    exit 2
fi
if [[ -n ${BUOY_SEED:-} && -z $scenario ]]; then
    echo "ERROR: BUOY_SEED requires SCENARIO." >&2
    exit 2
fi

ros_enabled=0
if [[ -n $scenario ]]; then
    case "$scenario" in
        one|gate|multi|repeated_red|slalom) ;;
        *) echo "ERROR: SCENARIO must be one, gate, multi, repeated_red, or slalom." >&2; exit 2 ;;
    esac
    mkdir -p logs/generated-worlds
    render_args=(
        --scenario "scenarios/$scenario.json"
        --base-world worlds/blueboat_rgbd_base.sdf
        --output-world logs/generated-worlds/active.sdf
        --manifest logs/generated-worlds/active.manifest.json
        --boat-model "${BOAT_MODEL:-single}"
    )
    if [[ -n ${BUOY_SEED:-} ]]; then
        render_args+=(--seed "$BUOY_SEED")
    fi
    python3 scripts/render_scenario.py "${render_args[@]}"
    export WORLD=active.sdf ROS_SIM=1 ENABLE_MAVROS=1 CAMERA_ENABLED=1
    ros_enabled=1
else
    mkdir -p logs/generated-worlds
    case "${ROS_SIM:-0}" in
        1|true|TRUE|yes|YES|on|ON)
            export ENABLE_MAVROS=1
            ros_enabled=1
            # Direct worlds must never reuse the previous scenario's entity roster.
            printf '%s\n' '{"name":"camera_only","buoys":[]}' > logs/generated-worlds/direct.json
            python3 scripts/render_scenario.py --scenario logs/generated-worlds/direct.json \
                --base-world worlds/blueboat_rgbd_base.sdf \
                --output-world logs/generated-worlds/direct.sdf \
                --manifest logs/generated-worlds/active.manifest.json --boat-model "${BOAT_MODEL:-single}"
            selected_world=${WORLD:-blueboat_waves.sdf}
            if [[ $selected_world == blueboat_rgbd_base.sdf ]]; then
                export CAMERA_ENABLED=1
            else
                export CAMERA_ENABLED=${CAMERA_ENABLED:-0}
            fi
            ;;
        0|false|FALSE|no|NO|off|OFF|"")
            export ENABLE_MAVROS=0 CAMERA_ENABLED=0
            ;;
        *) echo "ERROR: ROS_SIM must be a boolean value." >&2; exit 2 ;;
    esac
fi

if [[ -n ${BOAT_MODEL:-} ]]; then
    boat_source="worlds/${WORLD:-blueboat_waves.sdf}"
    [[ -z $scenario ]] || boat_source=logs/generated-worlds/active.sdf
    python3 scripts/render_boat.py --source "$boat_source" --output logs/generated-worlds/boat.sdf --boat-model "$BOAT_MODEL" \
        --manifest logs/generated-worlds/active.manifest.json
    export WORLD=boat.sdf
fi

if [[ -n ${WATER:-} ]]; then
    water_source="worlds/${WORLD:-blueboat_waves.sdf}"
    [[ -z $scenario ]] || water_source=logs/generated-worlds/active.sdf
    [[ -z ${BOAT_MODEL:-} ]] || water_source=logs/generated-worlds/boat.sdf
    water_args=(--source "$water_source" --output logs/generated-worlds/water.sdf --water "$WATER"
                --metadata logs/generated-worlds/water.json)
    python3 scripts/render_water.py "${water_args[@]}"
    export WORLD=water.sdf
fi

profile_args=()
if [[ $ros_enabled == 1 ]]; then
    profile_args=(--profile ros)
    export ADAPTER_ENVIRONMENT=simulation MARITIME_PREIMPLEMENTATION_PLACEHOLDER=1
fi

camera_model_dir=blueboat_rgbd
[[ ${BOAT_MODEL:-single} != dual ]] || camera_model_dir=blueboat_dual_rgbd
case $build_mode in
    no-cache)
        echo "Rebuilding $SIM_IMAGE without cache..."
        docker compose "${compose_files[@]}" "${profile_args[@]}" build --no-cache
        ;;
    always)
        echo "Rebuilding $SIM_IMAGE..."
        docker compose "${compose_files[@]}" "${profile_args[@]}" build
        ;;
    if-missing)
        need_build=0
        if ! docker image inspect "$SIM_IMAGE" >/dev/null 2>&1; then
            need_build=1
        elif [[ $CAMERA_ENABLED == 1 ]] && ! docker run --rm --entrypoint test "$SIM_IMAGE" -f "/opt/boat_sim/models/$camera_model_dir/model.sdf"; then
            need_build=1
        fi
        if [[ $ros_enabled == 1 ]]; then
            for ros_image in "$ADAPTER_IMAGE" "$AUTONOMY_IMAGE"; do
                if ! docker image inspect "$ros_image" >/dev/null 2>&1; then
                    need_build=1
                fi
            done
        fi
        if [[ $need_build == 1 ]]; then
            echo "Building required simulator images (the first build can take several minutes)..."
            docker compose "${compose_files[@]}" "${profile_args[@]}" build
        else
            echo "Reusing existing images"
        fi
        ;;
esac

if [[ $action == build ]]; then
    exit 0
fi

if [[ -z ${DISPLAY:-} ]]; then
    echo "ERROR: DISPLAY is empty. Run from the logged-in Linux desktop session." >&2
    exit 1
fi
if ! command -v xauth >/dev/null 2>&1; then
    echo "ERROR: xauth is required. Install it with: sudo apt install xauth" >&2
    exit 1
fi
if [[ ! -d /tmp/.X11-unix ]]; then
    echo "ERROR: /tmp/.X11-unix is unavailable; X11/Xwayland cannot be forwarded." >&2
    exit 1
fi

software=${SOFTWARE_RENDERING:-0}
case "${software,,}" in
    1|true|yes|on)
        export SOFTWARE_RENDERING=1 LIBGL_ALWAYS_SOFTWARE=1
        ;;
    0|false|no|off|"")
        export SOFTWARE_RENDERING=0 LIBGL_ALWAYS_SOFTWARE=0
        if [[ ! -d /dev/dri ]]; then
            echo "ERROR: /dev/dri is unavailable. Retry with SOFTWARE_RENDERING=1 make run" >&2
            exit 1
        fi
        ;;
    *) echo "ERROR: SOFTWARE_RENDERING must be a boolean value." >&2; exit 2 ;;
esac

mkdir -p logs
if [[ ! -w logs ]]; then
    echo "ERROR: $PROJECT_DIR/logs is not writable by UID $HOST_UID." >&2
    exit 1
fi

runtime_dir=${XDG_RUNTIME_DIR:-/tmp}
XAUTH_FILE=$(mktemp "$runtime_dir/ardupilot-blueboat-xauth.XXXXXX")
export XAUTH_FILE
printf '%s\n' "$XAUTH_FILE" > logs/active-xauth.path
container_started=0
log_pid=
export RUN_ID=$(date -u +%Y%m%dT%H%M%S)-$$
startup_timeout=${STACK_STARTUP_TIMEOUT:-180}
if [[ ! $startup_timeout =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: STACK_STARTUP_TIMEOUT must be a positive integer." >&2
    rm -f -- "$XAUTH_FILE" logs/active-xauth.path
    exit 2
fi
cleanup() {
    status=$?
    trap - EXIT INT TERM
    if [[ $container_started == 1 ]]; then
        docker compose "${compose_files[@]}" --profile ros down --remove-orphans || true
    fi
    if [[ -n $log_pid ]]; then
        kill "$log_pid" 2>/dev/null || true
        wait "$log_pid" 2>/dev/null || true
    fi
    rm -f -- "$XAUTH_FILE" logs/active-xauth.path
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cookie=$(xauth nlist "$DISPLAY" 2>/dev/null || true)
if [[ -z $cookie ]]; then
    echo "ERROR: no Xauthority cookie exists for DISPLAY=$DISPLAY." >&2
    exit 1
fi
printf '%s\n' "$cookie" | sed -e 's/^..../ffff/' | xauth -f "$XAUTH_FILE" nmerge -
chmod 0600 "$XAUTH_FILE"

display_number=${DISPLAY##*:}
display_number=${display_number%%.*}
if [[ ! -S /tmp/.X11-unix/X${display_number} ]]; then
    echo "ERROR: DISPLAY=$DISPLAY does not match /tmp/.X11-unix/X${display_number}." >&2
    exit 1
fi

echo "Host IDs: uid=$HOST_UID gid=$HOST_GID video_gid=$VIDEO_GID render_gid=$RENDER_GID"
echo "Boat model: ${BOAT_MODEL:-single}"
echo "World: ${WORLD:-blueboat_waves.sdf}; scenario: ${scenario:-none}; display: $DISPLAY"
echo "MAVLink: ${MAVLINK_QGC:-udp:127.0.0.1:14550} (QGC), ${MAVLINK_API:-udp:127.0.0.1:14551} (student API)"
if [[ $ros_enabled == 1 ]]; then
    echo "ROS 2: Simulation Adapter + pre-implementation autonomy bootstrap, domain ${ROS_DOMAIN_ID:-0}"
fi
if pgrep -f '[Q]GroundControl' >/dev/null 2>&1; then
    echo "QGroundControl is running and should auto-connect on UDP 14550."
else
    echo "Start /home/ppatel/Applications/QGroundControl-v5.1.4-x86_64.AppImage to use the ground station."
fi

# Save the resolved configuration and immutable scenario copy for this run.
# Placeholder launches allocate no persistent observation or map state.
export RUN_CONFIG_SHA256=recording
run_dir="logs/runs/$RUN_ID"
mkdir -p "$run_dir"
docker compose "${compose_files[@]}" "${profile_args[@]}" config > "$run_dir/compose.yaml"
export RUN_CONFIG_SHA256=$(sha256sum "$run_dir/compose.yaml" | cut -d ' ' -f1)
if [[ $ros_enabled == 1 && -f logs/generated-worlds/active.manifest.json ]]; then
    cp logs/generated-worlds/active.manifest.json "$run_dir/scenario.manifest.json"
fi
if [[ -n ${WATER:-} ]]; then
    cp logs/generated-worlds/water.json "$run_dir/water.json"
fi
printf 'run_id=%s\nconfiguration_sha256=%s\napplication_state=empty_simulation_placeholder\n' \
    "$RUN_ID" "$RUN_CONFIG_SHA256" > "$run_dir/identity.txt"

capture_failure() {
    echo "ERROR: $*; readiness and process evidence: $run_dir/failure.log" >&2
    docker compose "${compose_files[@]}" "${profile_args[@]}" ps -a > "$run_dir/failure.log" 2>&1 || true
    docker compose "${compose_files[@]}" "${profile_args[@]}" logs --tail=150 >> "$run_dir/failure.log" 2>&1 || true
    cat "$run_dir/failure.log" >&2
    return 1
}

wait_service() {
    local service=$1 category=$2 container=$3
    local deadline=$((SECONDS + startup_timeout))
    local state health prior
    while ((SECONDS < deadline)); do
        for prior in "${required_containers[@]}"; do
            state=$(docker inspect -f '{{.State.Status}}' "$prior" 2>/dev/null || true)
            if [[ $state != running ]]; then
                capture_failure "$category: preceding required service $prior exited"
                return 1
            fi
        done
        state=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || true)
        health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container" 2>/dev/null || true)
        [[ $state == running && $health == healthy ]] && return 0
        if [[ $state == exited || $state == dead ]]; then
            capture_failure "$category: $service exited during startup"
            return 1
        fi
        sleep 2
    done
    capture_failure "$category: $service readiness timed out after ${startup_timeout}s"
}

required_containers=()
container_started=1
docker compose "${compose_files[@]}" "${profile_args[@]}" up -d --no-deps --remove-orphans simulator
wait_service simulator gazebo_vehicle_sitl ardupilot-blueboat-sim
required_containers=(ardupilot-blueboat-sim)
if [[ $ros_enabled == 1 ]]; then
    docker compose "${compose_files[@]}" --profile ros up -d --no-deps adapter
    wait_service adapter camera_calibration_tf_fcu maritime-sim-adapter
    required_containers+=(maritime-sim-adapter)
    docker compose "${compose_files[@]}" --profile ros up -d --no-deps autonomy
    wait_service autonomy placeholder_liveness maritime-autonomy
    required_containers+=(maritime-autonomy)
fi
echo "Stack startup passed; placeholder mission/application readiness remains false. Run: $RUN_ID"
docker compose "${compose_files[@]}" "${profile_args[@]}" logs -f > "$run_dir/services.log" 2>&1 &
log_pid=$!
# Compose dependencies gate startup only. Continue supervising required services
# so a child exit or sustained semantic health failure terminates the whole run.
while true; do
    for container in "${required_containers[@]}"; do
        state=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || true)
        health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container" 2>/dev/null || true)
        if [[ $state != running || $health == unhealthy ]]; then
            capture_failure "required service $container failed: process=$state readiness=$health"
            exit 1
        fi
    done
    sleep 2
done

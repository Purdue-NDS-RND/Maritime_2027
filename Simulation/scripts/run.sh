#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_DIR"

build_mode=if-missing
action=up

usage() {
    cat <<'EOF'
Usage: make run|build|rebuild|down

Internal form: scripts/run.sh [--build|--build-only|--rebuild-only|--down|--help]

  no option       Start the simulation, building the image if absent
  --build         Rebuild the image, then start the simulation
  --build-only    Build the image without starting the simulation
  --rebuild-only  Force a clean image rebuild without starting
  --down          Stop and remove this project's container

Environment:
  SCENARIO=one|gate|multi  Render and launch an RGB-D buoy scenario with ROS
  BUOY_SEED=<integer>      Deterministically randomize the selected scenario
  ROS_SIM=1                Enable ROS/MAVROS for a direct WORLD launch
EOF
}

case "${1:-}" in
    "") ;;
    --build) build_mode=always ;;
    --build-only) build_mode=always; action=build ;;
    --rebuild-only) build_mode=no-cache; action=build ;;
    --down) action=down ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
esac

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
export FCU_URL=${FCU_URL:-udp://:14552@}

scenario=${SCENARIO:-}
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
        one|gate|multi) ;;
        *) echo "ERROR: SCENARIO must be one, gate, or multi." >&2; exit 2 ;;
    esac
    mkdir -p logs/generated-worlds
    render_args=(
        --scenario "scenarios/$scenario.json"
        --base-world worlds/blueboat_rgbd_base.sdf
        --output-world logs/generated-worlds/active.sdf
        --manifest logs/generated-worlds/active.manifest.json
    )
    if [[ -n ${BUOY_SEED:-} ]]; then
        render_args+=(--seed "$BUOY_SEED")
    fi
    python3 scripts/render_scenario.py "${render_args[@]}"
    ACTIVE_BUOY_IDS=$(python3 -c 'import json; print(",".join(str(item["marker_id"]) for item in json.load(open("logs/generated-worlds/active.manifest.json", encoding="utf-8"))["buoys"]))')
    export ACTIVE_BUOY_IDS
    export WORLD=active.sdf ROS_SIM=1 ENABLE_MAVROS=1 CAMERA_ENABLED=1
    ros_enabled=1
else
    mkdir -p logs/generated-worlds
    export ACTIVE_BUOY_IDS=
    case "${ROS_SIM:-0}" in
        1|true|TRUE|yes|YES|on|ON)
            export ENABLE_MAVROS=1
            ros_enabled=1
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

compose_files=(-f container/compose.yaml)
if [[ -d /dev/dri ]]; then
    compose_files+=(-f container/compose.gpu.yaml)
fi
profile_args=()
if [[ $ros_enabled == 1 ]]; then
    profile_args=(--profile ros)
fi

if [[ $action == down ]]; then
    docker compose "${compose_files[@]}" --profile ros down --remove-orphans
    exit 0
fi

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
        elif [[ $CAMERA_ENABLED == 1 ]] && ! docker run --rm --entrypoint test "$SIM_IMAGE" -f /opt/boat_sim/models/blueboat_rgbd/model.sdf; then
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
container_started=0
cleanup() {
    status=$?
    trap - EXIT
    if [[ $container_started == 1 ]]; then
        docker compose "${compose_files[@]}" --profile ros down --remove-orphans || true
    fi
    rm -f -- "$XAUTH_FILE"
    exit "$status"
}
trap cleanup EXIT

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
echo "World: ${WORLD:-blueboat_waves.sdf}; scenario: ${scenario:-none}; display: $DISPLAY"
echo "MAVLink: ${MAVLINK_QGC:-udp:127.0.0.1:14550} (QGC), ${MAVLINK_API:-udp:127.0.0.1:14551} (student API)"
if [[ $ros_enabled == 1 ]]; then
    echo "ROS 2: adapter + autonomy, domain ${ROS_DOMAIN_ID:-0}, FCU $FCU_URL"
fi
if pgrep -f '[Q]GroundControl' >/dev/null 2>&1; then
    echo "QGroundControl is running and should auto-connect on UDP 14550."
else
    echo "Start /home/ppatel/Applications/QGroundControl-v5.1.4-x86_64.AppImage to use the ground station."
fi

container_started=1
docker compose "${compose_files[@]}" "${profile_args[@]}" up --remove-orphans

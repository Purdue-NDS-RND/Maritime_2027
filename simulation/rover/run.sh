#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export HOST_UID=$(id -u) HOST_GID=$(id -g)
export ROVER_RUN_DIR="$PWD/logs/rover-sitl"
compose=(docker compose -f rover/compose.yaml)
case "${1:-run}" in
    build) "${compose[@]}" build ;;
    down) "${compose[@]}" down ;;
    logs) "${compose[@]}" logs -f ;;
    run)
        mkdir -p logs
        exec 9>logs/.launcher.lock
        flock -n 9 || { echo 'ERROR: another simulator launcher is active' >&2; exit 1; }
        # Never stop or attach to an existing simulator. Consumers on 14550/14551
        # are allowed; competing producers and JSON physics ports are not.
        if docker ps --format '{{.Names}}' | grep -Eq 'ardupilot-blueboat-sim|maritime-rover-sitl'; then
            echo 'ERROR: simulator already running; stop it explicitly first' >&2; exit 1
        fi
        if pgrep -x ardurrover >/dev/null || pgrep -f '[s]im_vehicle.py' >/dev/null || pgrep -f '[m]avproxy.py' >/dev/null; then
            echo 'ERROR: existing SITL/MAVProxy process; stop it explicitly first' >&2; exit 1
        fi
        mkdir -p "$ROVER_RUN_DIR"
        export ROVER_RUN_DIR=$(mktemp -d "$ROVER_RUN_DIR/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
        printf '%s\n' "$ROVER_RUN_DIR" > logs/rover-sitl/latest-run.txt
        if [[ -n ${XAUTHORITY:-} && -f $XAUTHORITY ]]; then export ROVER_XAUTH=$XAUTHORITY; fi
        "${compose[@]}" up -d --no-build
        container=$("${compose[@]}" ps -q rover)
        for _ in {1..125}; do
            health=$(docker inspect --format '{{.State.Health.Status}}' "$container")
            if [[ $health == healthy ]]; then
                echo "Rover ready: advancing Gazebo physics, ground-rover heartbeat and fresh GPS. Logs: $ROVER_RUN_DIR"
                exit 0
            fi
            state=$(docker inspect --format '{{.State.Status}}' "$container")
            [[ $state == running ]] || { "${compose[@]}" logs; exit 1; }
            sleep 1
        done
        echo "ERROR: rover readiness timed out; logs: $ROVER_RUN_DIR" >&2
        "${compose[@]}" down
        exit 1
        ;;
    smoke) "${compose[@]}" exec -T rover python3 /opt/rover/lifecycle.py ;;
    *) echo "unknown rover action: $1" >&2; exit 2 ;;
esac

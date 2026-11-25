#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export HOST_UID=$(id -u) HOST_GID=$(id -g)
if [[ -f ${XAUTHORITY:-${HOME}/.Xauthority} ]]; then
    export DRONE_XAUTH="${XAUTHORITY:-${HOME}/.Xauthority}"
fi
compose=(docker compose -f drone/compose.yaml)
case "${1:-run}" in
    build) ../scripts/with-build-provenance.sh "${compose[@]}" build ;;
    validate) "${compose[@]}" config --quiet ;;
    run)
        mkdir -p logs/drone-sitl
        "${compose[@]}" up -d --no-build --pull never --wait --wait-timeout 90
        printf 'Drone ready. MAVLink TCP 127.0.0.1:%s. Run logs: logs/drone-sitl/%s\n' \
            "${DRONE_MAVLINK_PORT:-5764}" "$(<logs/drone-sitl/latest-run.txt)"
        ;;
    down) "${compose[@]}" down ;;
    logs) "${compose[@]}" logs -f ;;
    gui)
        if [[ -z ${DISPLAY:-} ]]; then
            echo 'Drone GUI requires a local X11 display.' >&2
            exit 1
        fi
        "${compose[@]}" exec -T -e DISPLAY="$DISPLAY" drone bash -ec '
            export HOME="/sim/$(cat /sim/latest-run.txt)/state"
            export XDG_RUNTIME_DIR="$HOME/runtime"
            exec gz sim -g
        '
        ;;
    console)
        "${compose[@]}" exec drone bash -ec 'cd "/sim/$(cat /sim/latest-run.txt)"; exec mavproxy.py --master=tcp:127.0.0.1:5762 --logfile=mavlink.tlog'
        ;;
    camera)
        "${compose[@]}" exec -T drone python3 /opt/drone/camera_check.py "${@:2}"
        ;;
    *) printf 'Unknown drone action: %s\n' "$1" >&2; exit 2 ;;
esac

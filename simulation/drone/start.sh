#!/usr/bin/env bash
set -Eeuo pipefail
rm -f /tmp/drone-ready
run_dir=$(mktemp -d "/sim/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
printf '%s\n' "${run_dir##*/}" > /sim/latest-run.txt
cd "$run_dir"
cp /opt/drone/markers.csv .
export HOME="$run_dir/state"
export XDG_RUNTIME_DIR="$HOME/runtime"
mkdir -p -m 700 "$XDG_RUNTIME_DIR"

children=()
cleanup() {
    if (("${#children[@]}")); then
        kill "${children[@]}" 2>/dev/null || true
        wait "${children[@]}" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

gz sim -v 3 -r -s --headless-rendering /opt/drone/iris_competition.sdf > gazebo.log 2>&1 &
children+=("$!")
/opt/ardupilot/build/sitl/bin/arducopter --model JSON --speedup 1 \
    --home "$(</opt/drone/sitl-home.txt)" --serial0 tcp:0 --serial1 tcp:5762 \
    --defaults /opt/ardupilot/Tools/autotest/default_params/copter.parm,/opt/drone/iris.parm \
    > sitl.log 2>&1 &
children+=("$!")
echo "Starting Iris in $run_dir"
python3 /opt/drone/camera_check.py --ready &
probe=$!
children+=("$probe")
if ! wait -n -p finished "${children[@]}" || [[ ${finished:-} != "$probe" ]]; then
    echo "Iris failed to start. See $run_dir." >&2
    exit 1
fi
children=("${children[@]:0:2}")
touch /tmp/drone-ready
echo "Iris ready in $run_dir"
wait -n "${children[@]}" || true
echo "A simulator process exited. See $run_dir." >&2
exit 1

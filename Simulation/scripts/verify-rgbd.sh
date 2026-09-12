#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_DIR"

runner_pid=
stop_run() {
    if [[ -n ${runner_pid:-} ]] && kill -0 "$runner_pid" 2>/dev/null; then
        # A background shell may inherit SIGINT as ignored. Bringing Compose
        # down first makes its foreground `up` exit deterministically; TERM is
        # only a final nudge for the small wrapper shell.
        ./run.sh --down >/dev/null 2>&1 || true
        kill -TERM "$runner_pid" 2>/dev/null || true
        wait "$runner_pid" || true
    fi
    runner_pid=
    ./run.sh --down >/dev/null 2>&1 || true
}
trap stop_run EXIT INT TERM

wait_for_health() {
    local deadline=$((SECONDS + 150))
    while ((SECONDS < deadline)); do
        sim_health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' ardupilot-blueboat-sim 2>/dev/null || true)
        adapter_health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' maritime-sim-adapter 2>/dev/null || true)
        autonomy_health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' maritime-autonomy 2>/dev/null || true)
        [[ $sim_health == healthy && $adapter_health == healthy && $autonomy_health == healthy ]] && return 0
        kill -0 "$runner_pid" 2>/dev/null || break
        sleep 2
    done
    docker compose -f compose.yaml --profile ros logs --tail=150 >&2 || true
    return 1
}

run_case() {
    local scenario=$1
    local seed=${2:-}
    echo "=== Verifying RGB-D scenario: $scenario${seed:+ (seed $seed)} ==="
    if [[ -n $seed ]]; then
        SCENARIO="$scenario" BUOY_SEED="$seed" ./run.sh >"logs/verify-$scenario.log" 2>&1 &
    else
        SCENARIO="$scenario" ./run.sh >"logs/verify-$scenario.log" 2>&1 &
    fi
    runner_pid=$!
    wait_for_health
    docker exec ardupilot-blueboat-sim gz model --list | tee "logs/verify-$scenario-models.txt"
    if [[ $scenario == one || $scenario == gate ]]; then
        docker exec ardupilot-blueboat-sim python3 /opt/boat_sim/scripts/gazebo_sensor_smoke.py
        make sensor-smoke
    fi
    if [[ $scenario == one ]]; then
        make boundary-smoke
        make mavros-smoke
    fi
    stop_run
}

run_case one
run_case gate
run_case multi 42

echo "=== Verifying original ArduPilot behavior with the augmented boat and no buoys ==="
ROS_SIM=1 WORLD=blueboat_rgbd_base.sdf ./run.sh >logs/verify-camera-only.log 2>&1 &
runner_pid=$!
wait_for_health
# "ArduPilot Ready" precedes final redundant-IMU agreement on some GPU-loaded
# starts. Keep the established smoke test unchanged and give the two simulated
# gyros time to converge before its single arm request.
sleep 20
make smoke
stop_run

echo "Full RGB-D, scenario, MAVROS, and original-control verification passed."

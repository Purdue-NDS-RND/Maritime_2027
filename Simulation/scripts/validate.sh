#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_DIR"
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "$tmp_dir"' EXIT

scripts=(scripts/run.sh scripts/validate.sh scripts/smoke.sh scripts/verify-rgbd.sh scripts/gazebo_sensor_smoke.py container/start-sim.sh container/sitl-process-wrapper.sh container/healthcheck.sh)
bash -n "${scripts[@]}"
bash -n scripts/run-menu.sh
for script in "${scripts[@]}" scripts/smoke-test.py scripts/teleop_wasd.py; do
    [[ -x $script ]] || { echo "ERROR: $script is not executable" >&2; exit 1; }
done
python_sources=(
    scripts/smoke-test.py scripts/teleop_wasd.py scripts/augment_blueboat_model.py scripts/render_scenario.py scripts/gazebo_sensor_smoke.py
    scripts/render_boat.py tests/test_boat_models.py
    scripts/render_water.py tests/test_water_rendering.py tests/test_run_menu.py
    recordings/*.py tests/test_recordings.py tests/test_recording_menu.py
    ../Adapter/simulation/ros_ws/src/blueboat_sim_bringup/setup.py
    ../Adapter/simulation/ros_ws/src/blueboat_sim_bringup/launch/bringup.launch.py
    ../Adapter/simulation/ros_ws/src/blueboat_sim_bringup/blueboat_sim_bringup/*.py
    ../autonomy/ros_ws/src/maritime_bringup/setup.py
    ../autonomy/ros_ws/src/maritime_bringup/maritime_bringup/*.py
    ../autonomy/ros_ws/src/maritime_perception/setup.py
    ../autonomy/ros_ws/src/maritime_perception/maritime_perception/*.py
    ../autonomy/ros_ws/src/maritime_localization/setup.py
    ../autonomy/ros_ws/src/maritime_localization/maritime_localization/*.py
    ../autonomy/ros_ws/src/maritime_localization/launch/*.py
    ../autonomy/tools/navigation.py scripts/navigation_bridge.py tests/lifecycle_acceptance.py
    ../autonomy/ros_ws/src/maritime_navigation/maritime_navigation/*.py
    tests/evaluation/benchmarking/*.py
    ../tests/*.py
)
PYTHONPYCACHEPREFIX="$tmp_dir/pycache" python3 -m py_compile "${python_sources[@]}"

required=(
    container/Dockerfile ../Adapter/simulation/container/Dockerfile ../autonomy/container/Dockerfile
    ../deployment/compose.base.yaml
    container/compose.yaml container/compose.gpu.yaml Makefile
    ../Adapter/simulation/config/fastdds.xml
    config/blueboat.parm worlds/blueboat_waves.sdf worlds/blueboat_calm.sdf
    worlds/blueboat_harbor.sdf worlds/blueboat_rgbd_base.sdf
    scenarios/one.json scenarios/gate.json scenarios/multi.json scenarios/repeated_red.json scenarios/slalom.json
    models/blueboat_rgbd/model.config models/blueboat_rgbd/camera_payload.sdf
    plugins/CMakeLists.txt plugins/BuoyFaceBoat.cc
    ../Adapter/simulation/ros_ws/src/blueboat_sim_bringup/package.xml
    ../Adapter/simulation/ros_ws/src/blueboat_sim_bringup/config/bridge.yaml
    ../autonomy/ros_ws/src/maritime_bringup/package.xml
    README.md docs/SETUP.md docs/USING_THE_SIM.md docs/TROUBLESHOOTING.md docs/DEVELOPMENT.md
)
for path in "${required[@]}"; do
    [[ -f $path ]] || { echo "ERROR: required file missing: $path" >&2; exit 1; }
done

declare -A immutable_hashes=(
    [worlds/blueboat_calm.sdf]=aab2ac1d4b3d1515c288deb7c1431fa53f95ae9f972a7b5d52575517cf871ea1
    [worlds/blueboat_waves.sdf]=d9cf5589f6b314044a7feb0922d24b0bce3444951cbec8b9c17cb5db8b816c82
    [worlds/blueboat_harbor.sdf]=25392e067da365abe53a60547981559ad2eb8d9815b26b3f6cf3a054e50ba65f
    [config/blueboat.parm]=4ea8ca5d7198ac0338bc0e163075ae3997d13beb3e97488b1b449139ae741991
)
for path in "${!immutable_hashes[@]}"; do
    actual=$(sha256sum "$path" | cut -d' ' -f1)
    [[ $actual == "${immutable_hashes[$path]}" ]] || { echo "ERROR: protected baseline changed: $path" >&2; exit 1; }
done

pins=(
    1511f27194f1dcc3728270883047bdf022b3fd53
    082a0fe231f6e63bc8d1598f1cba461d9e2ea7f5
    25bc38ed8c6c0345840159a8cbc0b02781d52f3c
    ca8629df4e191235753dfae92ef725d30b923364
)
for pin in "${pins[@]}"; do
    grep -q "$pin" container/Dockerfile || { echo "ERROR: container/Dockerfile is missing source pin $pin" >&2; exit 1; }
    grep -q "$pin" container/compose.yaml || { echo "ERROR: container/compose.yaml is missing source pin $pin" >&2; exit 1; }
done

grep -q '<uri>model://blueboat</uri>' worlds/blueboat_waves.sdf
grep -q '<uri>model://blueboat</uri>' worlds/blueboat_calm.sdf
grep -q '<uri>model://blueboat</uri>' worlds/blueboat_harbor.sdf
grep -q '<amplitude>0.08</amplitude>' worlds/blueboat_waves.sdf
grep -q '<amplitude>0.0</amplitude>' worlds/blueboat_calm.sdf
grep -q '<amplitude>0.25</amplitude>' worlds/blueboat_harbor.sdf
grep -q '<model name="dock">' worlds/blueboat_harbor.sdf
grep -q '<collision name="deck_collision">' worlds/blueboat_harbor.sdf
grep -Eq '^FRAME_CLASS[[:space:]]+2$' config/blueboat.parm
grep -q 'fc651a9d4aff258fe675d94aeb24b91d82439cc441f99b00f921e316fbc3de57' container/Dockerfile
grep -q 'type="rgbd_camera"' models/blueboat_rgbd/camera_payload.sdf
grep -q '<width>1280</width>' models/blueboat_rgbd/camera_payload.sdf
grep -q '<height>720</height>' models/blueboat_rgbd/camera_payload.sdf
grep -q '<near>0.30</near><far>20.0</far>' models/blueboat_rgbd/camera_payload.sdf
grep -q 'udp://:14552@' container/compose.yaml

for scenario in one gate multi repeated_red slalom; do
    python3 scripts/render_scenario.py \
        --scenario "scenarios/$scenario.json" \
        --base-world worlds/blueboat_rgbd_base.sdf \
        --output-world "$tmp_dir/$scenario.sdf" \
        --manifest "$tmp_dir/$scenario.json"
    python3 scripts/render_scenario.py \
        --scenario "scenarios/$scenario.json" \
        --base-world worlds/blueboat_rgbd_base.sdf \
        --output-world "$tmp_dir/$scenario-seeded.sdf" \
        --manifest "$tmp_dir/$scenario-seeded.json" \
        --seed 42
done

for water in calm normal harsh; do
    python3 scripts/render_water.py --source "$tmp_dir/gate.sdf" \
        --output "$tmp_dir/gate-$water.sdf" --water "$water"
done

python3 - <<'PY'
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

payload = ET.parse('models/blueboat_rgbd/camera_payload.sdf')
ET.parse('../Adapter/simulation/config/fastdds.xml')
link = payload.find("./model/link[@name='base_link']")
assert link is not None
assert [child.tag for child in link] == ['visual', 'sensor']
assert all(child.tag not in {'collision', 'inertial'} for child in link)
for marker_id in range(4):
    root = Path(f'models/aruco_buoy_id{marker_id}')
    ET.parse(root / 'model.config')
    buoy = ET.parse(root / 'model.sdf')
    tracker = buoy.find("./model/plugin[@name='maritime::BuoyFaceBoat']")
    assert tracker is not None and tracker.get('filename') == 'libBuoyFaceBoat.so'
    assert tracker.findtext('boat_name') == 'blueboat'
    png = (root / 'materials/textures' / f'aruco_4x4_50_id{marker_id}.png').read_bytes()
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II', png[16:24]) == (512, 512)
for scenario in ('one', 'gate', 'multi', 'repeated_red', 'slalom'):
    data = json.loads(Path(f'scenarios/{scenario}.json').read_text())
    assert data['name'] == scenario and data['buoys']
print('Camera, buoy, texture, and scenario structure passed.')
PY

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    XAUTH_FILE=/dev/null DISPLAY=:0 HOST_UID=$(id -u) HOST_GID=$(id -g) \
        docker compose -f container/compose.yaml --profile ros config --quiet
    if docker image inspect ardupilot-blueboat:4.7.0 >/dev/null 2>&1; then
        for scenario in one gate multi repeated_red slalom gate-calm gate-normal gate-harsh; do
            cp "$tmp_dir/$scenario.sdf" "$tmp_dir/$scenario-resolved.sdf"
            sed -i \
                -e 's#model://blueboat_rgbd#file:///opt/boat_sim/models/blueboat_rgbd#g' \
                -e 's#model://aruco_buoy_id#file:///work/models/aruco_buoy_id#g' \
                "$tmp_dir/$scenario-resolved.sdf"
        done
        docker run --rm --entrypoint bash \
            -v "$PROJECT_DIR:/work:ro" -v "$tmp_dir:/validation:ro" \
            ardupilot-blueboat:4.7.0 -lc '
                set -e
                python3 /work/scripts/augment_blueboat_model.py \
                    --source /opt/SITL_Models/Gazebo/models/blueboat/model.sdf \
                    --payload /work/models/blueboat_dual_rgbd/camera_payload.sdf \
                    --output /tmp/blueboat_dual_rgbd/model.sdf --boat-model dual \
                    --expected-sha256 fc651a9d4aff258fe675d94aeb24b91d82439cc441f99b00f921e316fbc3de57
                gz sdf -k /tmp/blueboat_dual_rgbd/model.sdf >/dev/null
                for sdf in /validation/*-resolved.sdf /work/models/aruco_buoy_id*/model.sdf /opt/boat_sim/models/blueboat_rgbd/model.sdf; do
                    gz sdf -k "$sdf" >/dev/null
                done
            '
        echo "Gazebo SDF validation passed for generated worlds and added models."
    else
        echo "WARNING: simulator image is not built; skipped gz sdf -k checks." >&2
    fi
else
    echo "WARNING: Docker Compose is unavailable; skipped Compose resolution." >&2
fi

echo "Static validation passed."

python3 -m unittest discover -s tests -p test_boat_models.py -q

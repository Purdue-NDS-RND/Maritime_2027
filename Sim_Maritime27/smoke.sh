#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose is required." >&2
    exit 1
fi
if ! docker compose -f compose.yaml ps --status running --services | grep -qx simulator; then
    echo "ERROR: the simulator is not running. Start it with 'make run' in another terminal." >&2
    exit 1
fi

docker compose -f compose.yaml exec -T simulator python3 /opt/boat_sim/smoke-test.py

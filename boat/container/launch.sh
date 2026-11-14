#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

deployment=${1:?Choose sim or field}
if [[ "$deployment" != sim && "$deployment" != field ]]; then
    printf 'Unknown deployment: %s (choose sim or field)\n' "$deployment" >&2
    exit 1
fi
settings_file="$deployment.env"
if [[ ! -f "$settings_file" ]]; then
    printf 'Missing %s. See boat/README.md for setup.\n' "$settings_file" >&2
    if [[ -f "$settings_file.example" ]]; then
        printf '  cp %s.example %s\n' "$settings_file" "$settings_file" >&2
    fi
    exit 1
fi
# COMPOSE_FILE in the selected env supplies the base/optional serial YAML.
# Both modes use exactly the same validation and launch commands.
compose=(docker compose -p maritime-boat --env-file "$settings_file")

export HOST_UID=$(id -u)
export HOST_GID=$(id -g)
"${compose[@]}" config --quiet
# Both deployments share one project. Never replace an app that may own a mission.
running=$(docker ps -q --filter label=com.docker.compose.project=maritime-boat \
    --filter label=com.docker.compose.service=boat)
if [[ -n "$running" ]]; then
    printf '%s\n' 'A boat container is already running. Use make status to inspect it.' \
        'When ready to shut it down, use make down before starting another deployment.' >&2
    exit 1
fi

mkdir -p ../simulation/logs/boat/field-missions
exec "${compose[@]}" up --no-build

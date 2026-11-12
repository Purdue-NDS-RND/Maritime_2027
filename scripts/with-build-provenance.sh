#!/usr/bin/env bash
set -Eeuo pipefail
repository_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export MARITIME_SOURCE_REVISION=$(git -C "$repository_dir" rev-parse HEAD)
export MARITIME_SOURCE_BRANCH=$(git -C "$repository_dir" branch --show-current)
export MARITIME_SOURCE_DIRTY=false
if [[ -n $(git -C "$repository_dir" status --porcelain --untracked-files=normal) ]]; then
    export MARITIME_SOURCE_DIRTY=true
fi
exec "$@"

#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

if [[ "$#" -gt 1 || ( "$#" == 1 && "$1" != --print-unit ) ]]; then
    printf '%s\n' 'Usage: install-field-boot.sh [--print-unit]' >&2
    exit 1
fi
if [[ $(id -u) == 0 ]]; then
    printf '%s\n' 'Run make field-boot-install as the boat operator, without sudo.' >&2
    exit 1
fi
test -x /usr/bin/make
test -f field.env
unit_dir=$(mktemp -d)
unit_file="$unit_dir/maritime-boat-field.service"
trap 'rm -f -- "$unit_file"; rmdir -- "$unit_dir"' EXIT
python3 - "$PWD" "$(id -un)" > "$unit_file" <<'PY'
from pathlib import Path
import sys

boat_dir, operator = sys.argv[1:]
if any(character in boat_dir for character in '\n\r\\"'):
    raise SystemExit('Checkout path cannot contain newlines, backslashes or quotes.')
boat_dir = boat_dir.replace('%', '%%')

template = Path('container/maritime-boat-field.service.in').read_text()
print(template.replace('@USER@', operator)
      .replace('@BOAT_DIR@', boat_dir), end='')
PY
if [[ "${1:-}" == --print-unit ]]; then
    cat -- "$unit_file"
    exit 0
fi
# Fail before installation if this operator cannot access Docker or the image
# has not been built. Do not start a container or open a controller here.
docker info >/dev/null
docker image inspect maritime-boat:latest >/dev/null
systemd-analyze verify "$unit_file"
sudo install -m 0644 "$unit_file" /etc/systemd/system/maritime-boat-field.service
sudo systemctl daemon-reload
sudo systemctl enable maritime-boat-field.service
printf '%s\n' 'Field startup enabled for the next boot; no container was started.' \
    'To start now: sudo systemctl start maritime-boat-field' \
    'To inspect startup: journalctl -u maritime-boat-field -b'

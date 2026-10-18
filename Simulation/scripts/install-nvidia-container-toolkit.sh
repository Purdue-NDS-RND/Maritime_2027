#!/usr/bin/env bash
# Restore the official stable NVIDIA repository and missing container tools.
set -euo pipefail

for command in curl gpg apt-get; do
    command -v "$command" >/dev/null || { echo "ERROR: $command is required." >&2; exit 1; }
done
privilege=()
if [[ $EUID != 0 ]]; then
    command -v sudo >/dev/null || { echo 'ERROR: sudo is required.' >&2; exit 1; }
    privilege=(sudo)
fi

temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor > "$temporary/keyring.gpg"
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /' \
    > "$temporary/nvidia-container-toolkit.list"

echo 'Installing the official stable NVIDIA container packages; sudo may request your password.'
"${privilege[@]}" install -m 0644 "$temporary/keyring.gpg" /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
"${privilege[@]}" install -m 0644 "$temporary/nvidia-container-toolkit.list" /etc/apt/sources.list.d/nvidia-container-toolkit.list
"${privilege[@]}" apt-get update -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/nvidia-container-toolkit.list \
    -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0
"${privilege[@]}" apt-get install -y --no-install-recommends nvidia-container-toolkit
command -v nvidia-container-runtime
echo 'Toolkit installed. Docker was not restarted. See Simulation/docs/PERFORMANCE.md for the graphics probe.'

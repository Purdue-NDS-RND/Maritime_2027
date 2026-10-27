#!/usr/bin/env bash
# Sourced after the simulator image is available; never used by build or down.
select_simulation_gpu() {
    local requested=${SIM_GPU:-auto} probe
    case "$requested" in
        auto|mesa|nvidia) ;;
        *) echo 'ERROR: SIM_GPU must be auto, mesa, or nvidia.' >&2; return 2 ;;
    esac
    SIM_GPU_RESOLVED=mesa
    if [[ ${SOFTWARE_RENDERING:-0} == 1 ]]; then
        if [[ $requested == nvidia ]]; then
            echo 'ERROR: SIM_GPU=nvidia conflicts with SOFTWARE_RENDERING=1.' >&2
            return 2
        fi
        SIM_GPU_RESOLVED=software
        return
    fi
    [[ $requested != mesa ]] || return 0
    # A registered runtime is insufficient: OS upgrades can leave its Docker
    # entry behind while removing nvidia-container-runtime. Exercise it first.
    if [[ $requested == nvidia || -e /dev/nvidiactl ]]; then
        if probe=$(timeout 15 docker run --rm --runtime=nvidia \
            -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=utility \
            --entrypoint nvidia-smi "$SIM_IMAGE" -L 2>&1); then
            compose_files+=(-f container/compose.nvidia.yaml)
            SIM_GPU_RESOLVED=nvidia
        elif [[ $requested == nvidia ]]; then
            printf 'ERROR: NVIDIA container graphics is unavailable:\n%s\n' "$probe" >&2
            echo 'Install NVIDIA Container Toolkit, or select SIM_GPU=mesa.' >&2
            return 1
        else
            printf 'WARNING: NVIDIA GPU detected but its container runtime failed:\n%s\n' "$probe" >&2
            echo 'Using Mesa. See docs/PERFORMANCE.md to enable the discrete GPU.' >&2
        fi
    fi
}

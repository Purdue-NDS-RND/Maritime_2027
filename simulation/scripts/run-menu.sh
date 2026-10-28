#!/usr/bin/env bash
# Sourced by run.sh so choices feed the existing launch/validation path.

menu_read() {
    local prompt=$1
    if ! read -r -p "$prompt" menu_answer; then
        printf '\nSetup cancelled.\n'
        exit 0
    fi
    case "$menu_answer" in
        q|Q) printf 'Setup cancelled.\n'; exit 0 ;;
    esac
}

configure_simulation() {
    local menu_answer selection seed
    cat <<'EOF'

  BlueBoat simulation setup
  -------------------------
  Water conditions
  1) Calm            - flat water (default)
  2) Normal waves    - existing mild waves
  3) Harsh waves     - existing rough harbor waves

  Enter keeps the default. Type q at any prompt to cancel.

EOF
    while [[ -z ${WATER:-} ]]; do
        menu_read 'Choose water [1]: '
        case "${menu_answer:-1}" in
            1) export WATER=calm; break ;;
            2) export WATER=normal; break ;;
            3) export WATER=harsh; break ;;
            *) printf 'Please enter a number from 1 to 3, or q.\n' ;;
        esac
    done
    printf '\nWater preset: %s\n' "$WATER"
    cat <<'EOF'

  Setup / scene
  1) Open water      - boat only
  2) Harbor and dock - docking practice
  3) Single buoy     - one marker buoy
  4) Red/green gate  - a two-buoy gate
  5) Multiple buoys  - four buoys
  6) Repeated red    - two red buoys
  7) Camera only    - RGB-D camera, no buoys
  8) Slalom         - default; entry/exit gates and alternating red/green turns

EOF
    while true; do
        menu_read 'Choose a scene [8]: '
        selection=${menu_answer:-8}
        case "$selection" in
            1) export WORLD=blueboat_waves.sdf; break ;;
            2) export WORLD=blueboat_harbor.sdf; break ;;
            3) export SCENARIO=one; break ;;
            4) export SCENARIO=gate; break ;;
            5) export SCENARIO=multi; break ;;
            6) export SCENARIO=repeated_red; break ;;
            7) export WORLD=blueboat_rgbd_base.sdf CAMERAS=on; break ;;
            8) export SCENARIO=slalom; break ;;
            *) printf 'Please enter a number from 1 to 8, or q.\n' ;;
        esac
    done

    if [[ -n ${SCENARIO:-} ]]; then
        while true; do
            menu_read "Randomization seed [${BUOY_SEED:-Enter for fixed layout}]: "
            seed=${menu_answer:-${BUOY_SEED:-}}
            if [[ -z $seed || $seed =~ ^-?[0-9]+$ ]]; then
                if [[ -n $seed ]]; then
                    export BUOY_SEED=$seed
                fi
                break
            fi
            printf 'Please enter an integer, leave blank for the default, or q.\n'
        done
    fi

    [[ -z ${BOAT_MODEL:-} || -n ${CAMERAS:-} ]] || export CAMERAS=on
    if [[ -z ${CAMERAS:-} ]]; then
        while true; do
            menu_read 'Cameras off/on [off]: '
            case "${menu_answer:-off}" in
                off|on) export CAMERAS=${menu_answer:-off}; break ;;
                *) printf 'Please enter off or on, or q.\n' ;;
            esac
        done
    fi
    if [[ $CAMERAS == on && -z ${BOAT_MODEL:-} ]]; then
        while true; do
            menu_read 'Camera layout single/dual [single]: '
            case "${menu_answer:-single}" in
                single|dual) export BOAT_MODEL=${menu_answer:-single}; break ;;
                *) printf 'Please enter single or dual, or q.\n' ;;
            esac
        done
    fi
    if [[ -z ${MAVLINK_STREAMRATE:-} ]]; then
        while true; do
            menu_read 'Telemetry Hz 4/10/20 [4]: '
            case "${menu_answer:-4}" in
                4|10|20) export MAVLINK_STREAMRATE=${menu_answer:-4}; break ;;
                *) printf 'Please enter 4, 10 or 20, or q.\n' ;;
            esac
        done
    fi
}

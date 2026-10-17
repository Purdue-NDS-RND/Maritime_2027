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
    local menu_answer selection seed ros_default
    cat <<'EOF'

  BlueBoat simulation setup
  -------------------------
  Water conditions
  1) Calm            - flat water
  2) Normal waves    - existing mild waves (default)
  3) Harsh waves     - existing rough harbor waves

  Enter keeps the default. Type q at any prompt to cancel.

EOF
    while [[ -z ${WATER:-} ]]; do
        menu_read 'Choose water [2]: '
        case "${menu_answer:-2}" in
            1) export WATER=calm; break ;;
            2) export WATER=normal; break ;;
            3) export WATER=harsh; break ;;
            *) printf 'Please enter a number from 1 to 3, or q.\n' ;;
        esac
    done
    printf '\nWater preset: %s\n' "$WATER"
    cat <<'EOF'

  Setup / scene
  1) Open water      - boat only (default)
  2) Harbor and dock - docking practice
  3) Single buoy     - RGB-D camera and one marker buoy
  4) Red/green gate  - RGB-D camera and a two-buoy gate
  5) Multiple buoys  - RGB-D camera and four buoys
  6) Repeated red    - RGB-D camera and two red buoys
  7) Camera only    - RGB-D camera, no buoys
  8) Slalom         - entry/exit gates and alternating red/green turns

EOF
    while true; do
        menu_read 'Choose a scene [1]: '
        selection=${menu_answer:-1}
        case "$selection" in
            1) export WORLD=blueboat_waves.sdf; break ;;
            2) export WORLD=blueboat_harbor.sdf; break ;;
            3) export SCENARIO=one; break ;;
            4) export SCENARIO=gate; break ;;
            5) export SCENARIO=multi; break ;;
            6) export SCENARIO=repeated_red; break ;;
            7) export WORLD=blueboat_rgbd_base.sdf ROS_SIM=1; break ;;
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
    elif [[ $selection != 7 ]]; then
        ros_default=n
        case "${ROS_SIM:-0}" in
            1|true|TRUE|yes|YES|on|ON) ros_default=y ;;
        esac
        while true; do
            menu_read "Enable ROS/MAVROS (no camera in this world)? [y/n, default $ros_default]: "
            case "${menu_answer:-$ros_default}" in
                y|Y|yes|YES) export ROS_SIM=1; break ;;
                n|N|no|NO) export ROS_SIM=0; break ;;
                *) printf 'Please enter y, n, or q.\n' ;;
            esac
        done
    fi

    printf '\nStarting with: WATER=%q ' "$WATER"
    if [[ -n ${SCENARIO:-} ]]; then
        printf 'SCENARIO=%q ' "$SCENARIO"
        [[ -z ${BUOY_SEED:-} ]] || printf 'BUOY_SEED=%q ' "$BUOY_SEED"
    else
        printf 'WORLD=%q ROS_SIM=%q ' "$WORLD" "${ROS_SIM:-0}"
    fi
    printf 'make run\n\n'
}

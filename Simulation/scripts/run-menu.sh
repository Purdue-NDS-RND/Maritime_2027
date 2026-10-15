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
  1) Mild waves       - standard boat world (default)
  2) Calm water       - no waves
  3) Harbor and dock  - rough water, docking practice
  4) Single buoy      - RGB-D camera and one marker buoy
  5) Red/green gate   - RGB-D camera and a two-buoy gate
  6) Multiple buoys   - RGB-D camera and four buoys
  7) Repeated red     - RGB-D camera and two red buoys
  8) Camera only     - RGB-D camera, no buoys

  Enter keeps the default. Type q at any prompt to cancel.

EOF
    while true; do
        menu_read 'Choose a world [1]: '
        selection=${menu_answer:-1}
        case "$selection" in
            1) export WORLD=blueboat_waves.sdf; break ;;
            2) export WORLD=blueboat_calm.sdf; break ;;
            3) export WORLD=blueboat_harbor.sdf; break ;;
            4) export SCENARIO=one; break ;;
            5) export SCENARIO=gate; break ;;
            6) export SCENARIO=multi; break ;;
            7) export SCENARIO=repeated_red; break ;;
            8) export WORLD=blueboat_rgbd_base.sdf ROS_SIM=1; break ;;
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
    elif [[ $selection != 8 ]]; then
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

    printf '\nStarting with: '
    if [[ -n ${SCENARIO:-} ]]; then
        printf 'SCENARIO=%q ' "$SCENARIO"
        [[ -z ${BUOY_SEED:-} ]] || printf 'BUOY_SEED=%q ' "$BUOY_SEED"
    else
        printf 'WORLD=%q ROS_SIM=%q ' "$WORLD" "${ROS_SIM:-0}"
    fi
    printf 'make run\n\n'
}

def manual_mode_observed(state):
    return state is not None and state.mode == "MANUAL"

def guided_mode_observed(state):
    return state is not None and state.mode == "GUIDED"

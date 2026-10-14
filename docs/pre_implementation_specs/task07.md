# Task 07: Hardware Adapter Boundary — Deferred

**Status:** Deferred outside the pre-implementation simulation-foundation
milestone on 2026-09-15. This task is neither complete nor replaced by a
filesystem scaffold.

The repository's pre-implementation work prepares the simulation boundary for
future perception, state, and mapping work. It does not claim vessel deployment
support. `Adapter/hardware/` must remain absent until the inputs below are
available; an empty workspace, guessed transport, or generic camera placeholder
would make the repository appear more deployable than it is.

## Future Activation Gate

Reopen this task only when all of the following are supplied and can be reviewed:

- an approved target-platform decision and a supportable immutable ZED X Mini
  driver/SDK/wrapper combination for that target;
- the concrete capture-card topology and two-camera device/mounting
  configuration;
- the real FCU serial or network transport, including device mapping,
  permissions, reconnect behavior, and deployment override validation; and
- signed, contract-conforming dual-camera timing, registration, and trust-root
  evidence.

When reopened, the Hardware Adapter must implement the existing MAVROS and
camera contracts without simulation dependencies, must not expose simulation
truth, and must not arm, move, or command a vessel during validation. Its
implementation and deployment fragment are a future integration input; they are
not prerequisites for the current simulation-only Task 08–12 path.

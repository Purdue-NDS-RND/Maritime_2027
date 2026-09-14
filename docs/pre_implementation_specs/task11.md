# Task 11: Update Operational Guidance

**Goal:** Make all current contributor and operational documentation describe
the integrated ownership, paths, interfaces, and tested workflow accurately.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 9.

**Prerequisites:** Tasks 09 and 10 integrated with recorded verification
results.

**Exclusive write scope:**

- `AGENTS.md`
- `Adapter/README.md`
- `autonomy/README.md`
- `Simulation/README.md`
- `Simulation/docs/DEVELOPMENT.md`
- `Simulation/docs/SETUP.md`
- `Simulation/docs/RGBD_AND_BUOY_SCENARIOS.md`
- `deployment/README.md`
- `docs/High_Level_Design.md`
- `docs/Low_Level_Design.md`
- `docs/Things_To_Fix_Before_Implementation.md`
- Any other current Markdown containing a stale path/interface/ownership result
  found by the required repository-wide scan

This is the only task authorized to correct current operational Markdown. Do
not rewrite files under `docs/superpowers/plans/` or historical verification
reports.

## Required Work

- Document `Adapter/simulation/` and `Adapter/hardware/`, selected-Adapter
  ownership of MAVROS and cameras, and shared autonomy's exclusions.
- Document final image contents, startup handoffs, generic camera topics/frames,
  readiness meanings, evaluation-only truth, and simulation-only command smoke.
- Update build, run, join, test, and shutdown commands to match the integrated
  tree and recorded results.
- Scan all Markdown for flat `Adapter/` runtime paths, legacy public camera names,
  autonomy-owned `FCU_URL`, and autonomy-owned MAVROS instructions.
- Update checklist explanations only from merged code and available evidence;
  leave final section-10 checkbox status for Task 12. Add a superseded note to
  historical material when necessary; never rewrite old evidence as though it
  tested the new architecture.

## Acceptance

- Every documented path and command resolves in the current checkout.
- Current docs contain no stale ownership statements or legacy public camera
  interface instructions.
- Real-hardware steps are visibly separated from simulator steps and unverified
  hardware behavior is labeled unverified.
- Documentation distinguishes static validation, liveness, source readiness,
  FCU readiness, and semantic acceptance.
- Markdown link/path scans and `git diff --check` pass.

## Handoff

Return the exact searches used and explain every retained legacy term as either
private implementation detail or historical evidence.

# Task 03: Freeze the Scenario Entity and Category Contract

**Goal:** Separate simulated buoy identity from marker/category so repeated
categories remain distinct in rendering and evaluation.

**Source:** `Things_To_Fix_Before_Implementation.md`, section 1, "Scenario Entity
and Category Contract."

**Prerequisites:** None. May run in parallel with Tasks 01 and 02.

**Exclusive write scope:** Create
`docs/contracts/scenario_entity_contract.md`. Do not modify scenarios, the
renderer, bridges, evaluators, or the checklist.

## Required Work

- Define an immutable, unique entity identity independent of `marker_id` and
  category.
- Freeze category mapping `0 = white`, `1 = red`, `2 = green`, `3 = blue`.
- Define every required manifest field, validation rule, generated Gazebo name,
  and evaluation truth-topic name.
- Define how runtime bridge/evaluator configuration receives an identity-
  preserving entity roster without comma-separated marker IDs.
- State explicitly that autonomy receives categories and observations, never
  scenario entity IDs or truth positions.

## Acceptance

- Two different entity records may share a marker ID without sharing an entity
  name, generated model name, truth topic, or evaluator result key.
- The schema rejects duplicate entity identities but accepts repeated category
  marker IDs.
- The contract includes one complete example manifest containing two buoys of
  the same category.
- `rg -n "TBD|TODO|to be decided" docs/contracts/scenario_entity_contract.md`
  returns no matches.

## Handoff

List the old `ACTIVE_BUOY_IDS`, `buoy_<marker_id>`, and fixed bridge assumptions
that downstream tasks must remove.

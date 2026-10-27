# Migration validation — 2026-10-27

Historical evidence from the repository cleanup, not current runtime acceptance.
For current setup and available checks, see the [simulator guide](../../simulation/README.md).

Final checks ran after removing the entire adapter and ROS integration layer:

| Check | Result |
| --- | --- |
| `make validate` | Passed: shell/Python syntax, executable checks, protected model/parameter hashes, dependency pins, scenario/water generation, Compose resolution and Gazebo SDF parsing; 9 focused tests passed |
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 34 tests: 33 passed; NVIDIA host-device test skipped in sandbox (all 4 GPU tests passed in the host-visible validation run) |
| Directory/link/permission audit | Passed: README-only application scaffolds, no adapter or ROS evaluation directories, executable permissions preserved, local documentation links resolve |
| Compose base/GPU variants | Single `simulator` service with existing build and repository mount paths |
| Backup/worktree | Existing `revamp`; backup unchanged at `b1851a097f9715c9b0362cc2d3449f9ea681e33b`; original tracked worktree was clean |
| Local data | Existing simulator recordings/output and Monitor artifacts preserved under ignored `simulation/logs/`; editor settings retained |

Final static evidence is in `simulation/logs/revamp-final-validate.log`.
Configuration parsing and file checks do not prove live simulator behavior.

The user accepted the existing simulator as the baseline and requested a clean
restart without the adapter. Further live integration/lifecycle testing was
stopped. No final Docker rebuild or live control acceptance was run after that
simplification; no real-hardware or new GPS mission acceptance is claimed.

Before the final scope clarification, the old integration regression passed
single-buoy/gate sensor checks and MAVROS motion/HOLD/disarm. The first attempt
failed with a Gazebo Ogre material assertion at multi-buoy startup; the retry
passed multi-buoy roster checks and ended during repeated-red startup. Those
partial runs are not final-runtime acceptance. Their logs remain under
`simulation/logs/revamp-verify-rgbd*.log`. Test containers were cleaned up.

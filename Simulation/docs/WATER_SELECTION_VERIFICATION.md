# Water selection verification

Verified on 2026-10-16. Water is selected before scene setup. Presets reuse the
existing calm, waves, and harbor water parameters, applied to both physical and
visual wave definitions in a generated world. Boat assets and source worlds
are unchanged. Water metadata is separate from the strict scene manifest.

| Check | Result |
| --- | --- |
| Terminal menu tests | PASS: 10 tests, including cancellation, defaults, explicit configuration and prompt order |
| Water rendering tests | PASS: 3 tests covering 24 preset/scene combinations, source preservation, unchanged manifests and unsupported worlds |
| Scenario rendering tests | PASS: 9 tests |
| `make validate` | PASS, including Gazebo SDF checks for all three generated gate water variants |
| `make lifecycle-smoke` | PASS: all 11 cases, including loss of camera/FCU data, signals, duplicate launch protection and parameter persistence; original EEPROM restored |
| `WATER=normal make verify-rgbd` | PASS: complete scenario, RGB-D, MAVROS and original-control suite |

The normal-wave run passed 3,499 buoy-facing checks. Single-buoy, gate and
repeated-red RGB-D checks each received 100 exact triples at 30.30 Hz. The
seeded multi scene loaded all four entities. Boundary and MAVROS motion/stop
checks passed, as did the camera-only guided travel, return-home and disarm test.

Runtime evidence remains untracked under `logs/lifecycle-20261016T202820Z/` and
`logs/verify-*.log`. The suites stopped their simulation containers afterward.
Calm and harsh presets passed generated-world tests and SDF validation; the full
runtime suite above used normal waves. These are simulator results, not measured
sea-state calibration or hardware/autonomy readiness evidence.

# Navigation motion lattice

`lattice_diff_10cm.json` is derived from Nav2's Apache-2.0 licensed
`nav2_smac_planner/sample_primitives/5cm_resolution/0.5m_turning_radius/diff/output.json`,
distributed with ROS 2 Jazzy. Every metric length and XY coordinate is multiplied
by two; headings and topology are unchanged. This produces a 0.10 m grid,
1.0 m minimum curve radius, 16 headings and 112 primitives, including 32
in-place turns. Reverse expansion is disabled in `nav2.yaml`.

Source: <https://github.com/ros-navigation/navigation2/tree/jazzy/nav2_smac_planner/sample_primitives>
License: <https://github.com/ros-navigation/navigation2/blob/jazzy/LICENSE>
The license text is included in `NAV2-LICENSE.txt`.

The spatial scale does not tune boat dynamics. Nav2's polygon collision checker
and the supervisor's measured-motion hull sweep still apply. The lattice
resolution must match the planning grid and both Nav2 costmaps. Change all
three together if using another primitive set.

.DEFAULT_GOAL := help

export ROS_DOMAIN_ID ?= 0
export VIEW ?= plot
export POSE_CLOCK ?= receipt
export POSE_TOPIC ?= /mavros/local_position/odom
export POSE_TIME_OFFSET_S ?= 0

.PHONY: help mapping-build mapping mapping-view mapping-test
help:
	@printf '%s\n' \
	  'make mapping-build  Build the autonomy and optional live monitoring images' \
	  'make mapping        Run RGB detection, mapping and the live top-down popup' \
	  'make mapping VIEW=none  Run without a popup (RViz overlay still published)' \
	  'make mapping-view   Open only the viewer for an existing mapping session' \
	  'make mapping-test   Run clock, alignment and live pipeline tests' \
	  'Start Simulation and teleop separately as usual; Ctrl-C stops only this session.' \
	  'Settings: ROS_DOMAIN_ID=0 POSE_CLOCK=receipt|source POSE_TIME_OFFSET_S=0'

mapping-build:
	@python3 tools/live.py build

mapping:
	@python3 tools/live.py run

mapping-view:
	@python3 tools/live.py view

mapping-test:
	@python3 tools/live.py test

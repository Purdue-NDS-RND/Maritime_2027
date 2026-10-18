.DEFAULT_GOAL := help

export ROS_DOMAIN_ID ?= 0
export VIEW ?= plot
export POSE_CLOCK ?= receipt
export POSE_TOPIC ?= /mavros/local_position/odom
export POSE_TIME_OFFSET_S ?= 0

.PHONY: help mapping-build mapping mapping-view mapping-test
help:
	@printf '%s\n' \
	  'make navigation-build  Build navigation and its simulation support image' \
	  'make run             Run map-based Nav2 navigation (see docs/GATE_SLALOM_NAVIGATION.md)' \
	  'make navigation-test Run navigation and command-gate tests' \
	  'make mapping-build  Build the autonomy and optional live monitoring images' \
	  'make mapping        Run RGB detection, mapping and the live top-down popup' \
	  'make mapping VIEW=none  Run without a popup (RViz overlay still published)' \
	  'make mapping-view   Open only the viewer for an existing mapping session' \
	  'make mapping-test   Run clock, alignment and live pipeline tests' \
	  'Start Simulation separately. Use teleop only with passive mapping, not navigation.' \
	  'Mapping settings: ROS_DOMAIN_ID=0 POSE_CLOCK=receipt|source POSE_TIME_OFFSET_S=0'

mapping-build:
	@python3 tools/live.py build

mapping:
	@python3 tools/live.py run

mapping-view:
	@python3 tools/live.py view

mapping-test:
	@python3 tools/live.py test

.PHONY: run build navigation navigation-build navigation-test
run navigation:
	@python3 tools/navigation.py run --task $(or $(TASK),slalom) $(ARGS)

build navigation-build:
	@python3 tools/navigation.py build

navigation-test:
	@python3 tools/navigation.py test

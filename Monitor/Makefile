.DEFAULT_GOAL := help

export ROS_DOMAIN_ID ?= 0
export USE_SIM_TIME ?= false
ARGS ?=

.PHONY: help build shell topics nodes rviz rviz-sim graph config validate smoke

help:
	@printf '%s\n' \
	  'Run from Monitor/ (or use make -C Monitor from the repository root):' \
	  '  make build       Build/update the tools image' \
	  '  make shell       Open a Bash terminal with ROS 2 ready' \
	  '  make topics      List ROS topics' \
	  '  make nodes       List ROS nodes' \
	  '  make rviz        Open the testing preset using wall time by default' \
	  '  make rviz-sim    Open the world, boat, buoys and camera simulation view' \
	  '  make graph       Open rqt_graph' \
	  '  make config      Print resolved container configuration' \
	  '  make validate    Check launcher syntax and Compose configuration' \
	  '  make smoke       Test cross-container data delivery (build first)' \
	  '' \
	  'Settings: ROS_DOMAIN_ID=0, USE_SIM_TIME=false' \
	  'Graphics fallback: LIBGL_ALWAYS_SOFTWARE=1' \
	  'Extra command/flags: ARGS="ros2 topic list" or ARGS="-d /logs/view.rviz"' \
	  'Examples: make topics ROS_DOMAIN_ID=12; make rviz-sim LIBGL_ALWAYS_SOFTWARE=1' \
	  'Exit shell with exit/Ctrl-D; close a GUI window to end its container.'

build:
	@./scripts/monitor build $(ARGS)

shell:
	@./scripts/monitor shell $(ARGS)

topics:
	@./scripts/monitor shell ros2 topic list $(ARGS)

nodes:
	@./scripts/monitor shell ros2 node list $(ARGS)

rviz:
	@./scripts/monitor rviz $(ARGS)

rviz-sim:
	@USE_SIM_TIME=true ./scripts/monitor rviz-sim $(ARGS)

graph:
	@./scripts/monitor gui rqt_graph $(ARGS)

config:
	@./scripts/monitor config $(ARGS)

validate:
	@bash -n scripts/monitor scripts/smoke container/entrypoint.sh tools/rviz-simulation
	@python3 -c 'import ast,sys; [ast.parse(open(p).read(), filename=p) for p in sys.argv[1:]]' tools/*.py tests/*.py
	@./scripts/monitor config --quiet
	@printf '%s\n' 'Monitor launcher syntax and Compose configuration passed.'

smoke:
	@./scripts/smoke

.PHONY: run build rebuild ros-build validate smoke teleop sensor-smoke mavros-smoke boundary-smoke verify-rgbd down logs

run:
	./scripts/run.sh

build:
	./scripts/run.sh --build-only

rebuild:
	./scripts/run.sh --rebuild-only

ros-build:
	ROS_SIM=1 ./scripts/run.sh --build-only

validate:
	./scripts/validate.sh

smoke:
	./scripts/smoke.sh

teleop:
	@docker compose -f container/compose.yaml ps --status running --services | grep -qx simulator || { printf '%s\n' "ERROR: simulator is not running. Start it with 'make run' first." >&2; exit 1; }
	@docker run --rm -it --network host \
		--user 0 \
		$(foreach device,$(wildcard /dev/input/event*),--device $(device)) \
		-v "$(CURDIR)/scripts/teleop_wasd.py:/tmp/teleop_wasd.py:ro" \
		--entrypoint python3 "$${SIM_IMAGE:-ardupilot-blueboat:4.7.0}" /tmp/teleop_wasd.py

sensor-smoke:
	docker compose -f container/compose.yaml --profile ros --profile evaluation run --rm --no-deps -e SIMULATION_EVALUATION=1 evaluation ros2 run blueboat_sim_evaluation sensor_smoke

mavros-smoke:
	docker compose -f container/compose.yaml --profile ros --profile evaluation run --rm --no-deps -e SIMULATION_EVALUATION=1 evaluation ros2 run blueboat_sim_evaluation mavros_smoke

boundary-smoke:
	docker compose -f container/compose.yaml --profile ros --profile evaluation run --rm --no-deps -T -e SIMULATION_EVALUATION=1 evaluation python3 - < ../tests/ros_boundary_smoke.py

verify-rgbd:
	./scripts/verify-rgbd.sh

down:
	./scripts/run.sh --down

logs:
	docker compose -f container/compose.yaml --profile ros logs -f

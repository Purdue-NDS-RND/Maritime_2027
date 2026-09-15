.PHONY: run build rebuild ros-build validate smoke sensor-smoke mavros-smoke boundary-smoke verify-rgbd down logs

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

sensor-smoke:
	docker compose -f container/compose.yaml --profile evaluation run --rm -e SIMULATION_EVALUATION=1 evaluation ros2 run blueboat_sim_evaluation sensor_smoke

mavros-smoke:
	docker compose -f container/compose.yaml --profile evaluation run --rm -e SIMULATION_EVALUATION=1 evaluation ros2 run blueboat_sim_evaluation mavros_smoke

boundary-smoke:
	docker exec -i maritime-autonomy bash -lc 'source /etc/maritime_autonomy_setup.bash && python3 -' < ../tests/ros_boundary_smoke.py

verify-rgbd:
	./scripts/verify-rgbd.sh

down:
	./scripts/run.sh --down

logs:
	docker compose -f container/compose.yaml --profile ros logs -f

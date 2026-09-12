.PHONY: run build rebuild ros-build validate smoke sensor-smoke mavros-smoke boundary-smoke verify-rgbd down logs

run:
	./run.sh

build:
	./run.sh --build-only

rebuild:
	./run.sh --rebuild-only

ros-build:
	ROS_SIM=1 ./run.sh --build-only

validate:
	./validate.sh

smoke:
	./smoke.sh

sensor-smoke:
	docker exec maritime-sim-adapter bash -lc 'source /etc/blueboat_ros_setup.bash && ros2 run blueboat_sim_bringup sensor_smoke'

mavros-smoke:
	docker exec maritime-sim-adapter bash -lc 'source /etc/blueboat_ros_setup.bash && ros2 run blueboat_sim_bringup mavros_smoke'

boundary-smoke:
	docker exec -i maritime-autonomy bash -lc 'source /etc/maritime_autonomy_setup.bash && python3 -' < ../tests/ros_boundary_smoke.py

verify-rgbd:
	./scripts/verify-rgbd.sh

down:
	./run.sh --down

logs:
	docker compose -f compose.yaml --profile ros logs -f

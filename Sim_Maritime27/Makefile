.PHONY: run build rebuild ros-build validate smoke sensor-smoke mavros-smoke verify-rgbd down logs

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
	docker exec ardupilot-blueboat-ros bash -lc 'source /etc/blueboat_ros_setup.bash && ros2 run blueboat_sim_bringup sensor_smoke'

mavros-smoke:
	docker exec ardupilot-blueboat-ros bash -lc 'source /etc/blueboat_ros_setup.bash && ros2 run blueboat_sim_bringup mavros_smoke'

verify-rgbd:
	./scripts/verify-rgbd.sh

down:
	./run.sh --down

logs:
	docker compose -f compose.yaml --profile ros logs -f

.DEFAULT_GOAL := validate
.PHONY: validate test build run down status upload start stop disarm

validate:
	python3 -m unittest discover -s tests -p 'test_mission.py' -v
	python3 -m compileall -q boat_app tests
	bash -n container/entrypoint.sh
	docker compose -f container/compose.yaml config --quiet

build:
	docker compose -f container/compose.yaml build

test:
	docker run --rm --network none "$${BOAT_IMAGE:-maritime-boat:latest}" python3 -m unittest discover -s /ws/src/boat_app/tests -v

run:
	mkdir -p ../simulation/logs/boat ../simulation/logs/profiles
	HOST_UID=$$(id -u) HOST_GID=$$(id -g) docker compose -f container/compose.yaml up --no-build

down:
	docker compose -f container/compose.yaml down

status:
	docker compose -f container/compose.yaml exec -T boat /boat-entrypoint.sh ros2 topic echo /boat_mission/status

upload start stop disarm:
	docker compose -f container/compose.yaml exec -T boat /boat-entrypoint.sh python3 -m boat_app.client $@

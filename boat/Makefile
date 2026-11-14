.DEFAULT_GOAL := validate
COMPOSE = docker compose -p maritime-boat --env-file sim.env -f container/compose.yaml
.PHONY: help validate test build sim field run down status upload start stop disarm

help:
	@printf '%s\n' 'make build   Build the image for this computer' 'make sim     Start the boat app for simulation' 'make field   Start with field.env and the physical Pixhawk' 'make status  Watch the running boat status' 'make stop    Request HOLD' 'make down    Shut down the boat container' 'make test    Run tests without a vehicle'

validate:
	python3 -m unittest discover -s tests -p 'test_mission.py' -v
	python3 -m unittest discover -s tests -p 'test_launch.py' -v
	python3 -m compileall -q boat_app tests
	bash -n container/entrypoint.sh container/launch.sh
	docker compose -p maritime-boat --env-file sim.env config --quiet
	BOAT_SERIAL_DEVICE=/dev/null BOAT_SERIAL_GID=0 BOAT_BAUD=115200 BOAT_HTTP_HOST=127.0.0.1 docker compose -p maritime-boat --env-file field.env.example config --quiet

build:
	../scripts/with-build-provenance.sh $(COMPOSE) build

test:
	docker run --rm --network none "$${BOAT_IMAGE:-maritime-boat:latest}" python3 -m unittest discover -s /ws/src/boat_app/tests -v

run: sim

sim field:
	bash container/launch.sh $@

down:
	$(COMPOSE) down

status:
	$(COMPOSE) exec -T boat /boat-entrypoint.sh ros2 topic echo /boat_mission/status

upload start stop disarm:
	$(COMPOSE) exec -T boat /boat-entrypoint.sh python3 -m boat_app.client $@

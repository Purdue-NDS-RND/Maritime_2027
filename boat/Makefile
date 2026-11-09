.DEFAULT_GOAL := validate
ENV_FILE ?=
SERIAL ?= 0
COMPOSE = docker compose $(if $(ENV_FILE),--env-file "$(ENV_FILE)") -f container/compose.yaml $(if $(filter 1,$(SERIAL)),-f container/compose.serial.yaml)
.PHONY: validate test build run down status upload start stop disarm

validate:
	python3 -m unittest discover -s tests -p 'test_mission.py' -v
	python3 -m compileall -q boat_app tests
	bash -n container/entrypoint.sh
	$(COMPOSE) config --quiet

build:
	$(COMPOSE) build

test:
	docker run --rm --network none "$${BOAT_IMAGE:-maritime-boat:latest}" python3 -m unittest discover -s /ws/src/boat_app/tests -v

run:
	mkdir -p ../simulation/logs/boat
	HOST_UID=$$(id -u) HOST_GID=$$(id -g) $(COMPOSE) up --no-build

down:
	$(COMPOSE) down

status:
	$(COMPOSE) exec -T boat /boat-entrypoint.sh ros2 topic echo /boat_mission/status

upload start stop disarm:
	$(COMPOSE) exec -T boat /boat-entrypoint.sh python3 -m boat_app.client $@

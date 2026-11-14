.DEFAULT_GOAL := validate
ENV_FILE ?=
SERIAL ?= 0
COMPOSE = docker compose $(if $(ENV_FILE),--env-file "$(ENV_FILE)") -f container/compose.yaml $(if $(filter 1,$(SERIAL)),-f container/compose.serial.yaml)
.PHONY: build run down validate test
build:
	$(COMPOSE) build
run:
	mkdir -p ../simulation/logs/gcs
	HOST_UID=$$(id -u) HOST_GID=$$(id -g) $(COMPOSE) up --build
down:
	$(COMPOSE) down
validate:
	PYTHONPATH=.. python3 -m unittest discover -s tests -v
	python3 -m compileall -q app
	cd frontend && npm ci && npm test && npm run build
	$(COMPOSE) config --quiet

test:
	docker build -f container/Dockerfile.test --build-arg GCS_TEST_BASE="$${GCS_IMAGE:-maritime-gcs:latest}" -t "$${GCS_TEST_IMAGE:-maritime-gcs:test}" ..
	docker run --rm --network none "$${GCS_TEST_IMAGE:-maritime-gcs:test}"

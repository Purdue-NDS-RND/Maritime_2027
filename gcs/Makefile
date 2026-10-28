.DEFAULT_GOAL := validate
.PHONY: build run down validate test
build:
	docker compose -f container/compose.yaml build
run:
	mkdir -p ../simulation/logs/gcs ../simulation/logs/profiles
	HOST_UID=$$(id -u) HOST_GID=$$(id -g) docker compose -f container/compose.yaml up --no-build
down:
	docker compose -f container/compose.yaml down
validate:
	PYTHONPATH=.. python3 -m unittest discover -s tests -v
	python3 -m compileall -q app
	cd frontend && npm ci && npm run build
	docker compose -f container/compose.yaml config --quiet

test:
	docker build -f container/Dockerfile.test --build-arg GCS_TEST_BASE="$${GCS_IMAGE:-maritime-gcs:latest}" -t "$${GCS_TEST_IMAGE:-maritime-gcs:test}" ..
	docker run --rm --network none "$${GCS_TEST_IMAGE:-maritime-gcs:test}"

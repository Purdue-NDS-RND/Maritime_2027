.DEFAULT_GOAL := run

.PHONY: run random-course build build-cached rebuild validate smoke teleop sensor-smoke buoy-tracking-smoke down logs

run:
	@./scripts/run.sh

# Development tool only: writes a new bundle, never starts/replaces a runtime.
random-course:
	@set --; [ -z "$${ROTATION:-}" ] || set -- "$$@" --rotation-deg "$$ROTATION"; \
	[ "$${CHECK:-0}" != 1 ] || set -- "$$@" --check-compiler; \
	python3 scripts/generate_course.py --seed "$${SEED:-42}" --variation "$${VARIATION:-moderate}" "$$@"

build:
	./scripts/run.sh --build-only

# Rebuild application/plugin sources over verified immutable source checkouts.
# Uses the installed canonical runtime as its verified dependency base.
build-cached:
	docker build -f container/Dockerfile.cached \
		--build-arg BASE_IMAGE="$${BASE_IMAGE:-maritime-sim:latest}" \
		-t "$${SIM_IMAGE:-maritime-sim:latest}" .

rebuild:
	./scripts/run.sh --rebuild-only

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
		--entrypoint python3 "$${SIM_IMAGE:-maritime-sim:latest}" /tmp/teleop_wasd.py

sensor-smoke:
	docker compose -f container/compose.yaml exec -T simulator python3 /opt/boat_sim/scripts/gazebo_sensor_smoke.py

buoy-tracking-smoke:
	@mkdir -p logs
	docker run --rm -e GZ_PARTITION=buoy_tracking_test --entrypoint bash \
		-v "$(CURDIR)/tests/buoy_tracking:/test:ro" "$${SIM_IMAGE:-maritime-sim:latest}" \
		-lc 'cmake -S /test -B /tmp/buoy-test && cmake --build /tmp/buoy-test -j2 && /tmp/buoy-test/buoy_tracking_test /tmp/tracking.sdf'

down:
	./scripts/run.sh --down

logs:
	docker compose -f container/compose.yaml logs -f

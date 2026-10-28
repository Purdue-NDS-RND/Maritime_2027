.DEFAULT_GOAL := run

.PHONY: run build build-cached rebuild validate smoke teleop sensor-smoke buoy-tracking-smoke down logs

run:
	@./scripts/run.sh

build:
	./scripts/run.sh --build-only

# Rebuild application/plugin sources over verified immutable source checkouts.
# Keep the original simulator image tag available for rollback.
build-cached:
	docker build -f container/Dockerfile.cached \
		--build-arg BASE_IMAGE="$${BASE_IMAGE:-ardupilot-blueboat:4.7.0}" \
		-t "$${SIM_IMAGE:-maritime-milestone1-sim:current}" .

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
		--entrypoint python3 "$${SIM_IMAGE:-ardupilot-blueboat:4.7.0}" /tmp/teleop_wasd.py

sensor-smoke:
	docker compose -f container/compose.yaml exec -T simulator python3 /opt/boat_sim/scripts/gazebo_sensor_smoke.py

buoy-tracking-smoke:
	@mkdir -p logs
	docker run --rm -e GZ_PARTITION=buoy_tracking_test --entrypoint bash \
		-v "$(CURDIR)/tests/buoy_tracking:/test:ro" "$${SIM_IMAGE:-ardupilot-blueboat:4.7.0}" \
		-lc 'cmake -S /test -B /tmp/buoy-test && cmake --build /tmp/buoy-test -j2 && /tmp/buoy-test/buoy_tracking_test /tmp/tracking.sdf'

down:
	./scripts/run.sh --down

logs:
	docker compose -f container/compose.yaml logs -f

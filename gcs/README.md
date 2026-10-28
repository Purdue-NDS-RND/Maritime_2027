# Course GCS

React + Leaflet and FastAPI, served together at <http://localhost:8080>.
Course editing works without internet tiles. Optional OpenStreetMap tiles
include attribution; tile failure leaves the route workspace available.

From `gcs/`:

```bash
make build
make run
make down
```

Runtime data lives under ignored `simulation/logs/gcs/`. Mount measured profile
JSON files read-only from `simulation/logs/profiles/`. No production profile is
shipped: a synthetic test fixture must never be installed as a live profile.
See [the implementation handoff](../docs/milestone1_handoff.md).

Import the JSON produced by `simulation/scripts/export_active.py`. Click to add
GPS waypoints, drag them, edit coordinates, reorder or delete them. Explicitly
select the finish centre using the last waypoint and choose ordered gate/turn
roles. `left`/`right` mean the boat passes on that side of the buoy when travelling
along the fixed course's +X direction. This validator supports that course
orientation; it rejects other gate orientations.

Save the draft, then use **Validate**, **Approve**, **Upload**, and **Start** as
separate actions. Every edit revokes approval. Immutable approved JSON files
include the imported map, settings, profile, validation and transfer envelope.
A changed profile invalidates approval even without browser edits. Reload
restores saved drafts and approvals. Unsaved edits are identified in the UI.

The backend validates both the planned start connection and the actual boat
position at upload and start. Clearance uses an enclosing boat circle plus the
selected clearance, measured position/tracking allowance and 0.10 m reserve.
Finish-region validation also includes its radius. No route is generated,
waypoint changed or clearance reduced by validation.

The browser talks only to the GCS backend. The backend talks only to the boat's
loopback HTTP API on port 8091, never directly to MAVLink. A 202 response means
receipt; query the returned operation ID for confirmation. After an ambiguous
start timeout, inspect operation and vehicle status instead of issuing a new
mission. Reconnecting never starts a mission automatically. STOP remains
available independently of draft/approval; disarm is checked by the boat.

Tests: `PYTHONPATH=.. python3 -m unittest discover -s tests -v` and
`cd frontend && npm ci && npm run build`. Container builds use the committed
npm lockfile. These are development loopback interfaces, not a selected
physical vehicle networking or authentication design.

# Map cleanup and course compilation

Status: implemented on `feature/map-compiling`. This is observation recognition
and operator-reviewed planning, not physical-boat or competition qualification.

Seeded full-course test inputs and matching Gazebo layouts are available through
`make random-course SEED=45` in `simulation/`. See
[random course testing](../simulation/docs/USING_THE_SIM.md#random-full-course-layouts)
for rotation, bends, stagger, skew and variation constraints. Simulator truth is
kept separate from shuffled GPS observations; recognition receives no role hints.

## Operator workflow

Map presents one step at a time: **Clean up → Find course → Review tasks**.
The next action stays at the bottom of the panel while longer details scroll.

1. **Import.** Load native maps, simple JSON/CSV observations, or saved course
   JSON. `gcs/examples/competition-gps-points.json` is the full 29-object example
   without meaningful IDs or types. To replace an imported map, open **Change
   map / source details**. Capture/import timestamps also live there.
2. **Clean up.** If red/green observations still have unknown types, the screen
   offers **Mark N red/green detections as buoys**. This explicit action changes
   only unknown red/green point/circular observations; it preserves known towers
   and obstacles. Use **Choose detections by color** for an individual selection.
   Click an object to edit its color/type or remove it. Position, dimensions and
   original observation are inside the object's details. Add missing points with
   **Add object on map**. IDs track observations and never describe course roles.
3. Use **Undo map edit**, **Redo map edit**, or **Compare with the original map**
   when needed. Original observations remain separate and immutable. Undo/redo
   retains 100 snapshots and never restores recognition or route authority.
4. **I reviewed the map — continue** explicitly confirms map review and opens
   **Find course**. At least two typed red/green navigation buoys are required
   for this path. **Map checked — assign tasks manually** keeps manual planning
   available for other maps. Unknown and other objects still block routes.
5. **Compile course** finds proposed tasks and opens **Review tasks**. A file
   with saved assignments can instead use **Review existing assignments**.
   Finding a course preserves all GPS positions and does not generate routes.
6. Select **Option 1–5** to preview alternatives. Inspect highlighted gate pairs,
   numbered slalom turns and channel chains, then **Confirm Gate**, **Confirm
   Slalom** and/or **Confirm Channel**. A confirmed row changes its status;
   there is no second template list to review. Confirm any useful subset and
   leave other tasks unresolved. Conflicting selections remain rejected.
7. Optional controls stay collapsed: **Objects & corrections** lists assigned
   observations and clears a selection; **Wrong objects? Add a hint** pins a
   selected observation before recompiling; **Measurements & search details**
   exposes costs, unusual spacing, incomplete results and resource limits.
   The starting pair retains the historical `slalom.entrance.*` role names as
   recognition anchors; its crossing belongs only to the separate Gate task.
   Slalom's object list and map overlay show the turns and exit gate.
   Recompilation clears
   earlier confirmations. Costs are not probabilities; bounded searches may
   omit other interpretations.
8. **Continue to Configure** opens navigation settings after at least one task
   is confirmed. The explicit manual-assignment link can bypass recognition.
   Choose start, boundary, clearance and budget; then add cards in **Build run**.
   Review local directions, suggested finish and channel water, and confirm
   each task card. Add Gate then Slalom to include both, or Slalom alone to
   start with its turns. They remain separate blocks without crossing sharing.
   **Generate → Validate → Approve → Upload/readback → Start** remain separate.

**Save course** at the bottom opens **Download course JSON**. It saves the
original/cleaned observations, profile, hints and chosen roles. Reimport requires
map review and task confirmation again. Confirming a Map task only selects its
assignments; task geometry/finish and route review still happen in the builder.

Manual task assignment is available without compiling. Recognition never moves,
merges, deletes or invents observations. A recognized course may be impossible
at the selected required clearance; the planner does not lower that clearance.
Finishes use the existing clearance-aware suggestion, including a Channel finish
past the actual final gate. The suggested channel polygon and directions still
require review; recognition does not establish the true permitted water.

## Reference profile and ranking

`gcs/app/course_profile.py` defines profile `aimm-course-concepts`, version 1,
from [Course and Competition Details](<competition_docs/Course and Competition Details.pdf>),
principally the course map and Dodge/Evade diagrams. This supplied historical
concept document is design context, not confirmed final event rules.

- Slalom: entrance gate, four alternating red/green turns, exit gate; nominal
  successive spacing **30 ft = 9.144 m**.
- Starting gate aliases the same physical slalom entrance pair.
  This recognition alias does not require a crossing in the Slalom route;
  the separate Gate task owns that crossing.
- Channel: three red and three green observations, width **40 ft = 12.192 m**,
  length **60 ft = 18.288 m**, nominal adjacent boundary spacing 30 ft.
- Connection: illustrated **15 ft = 4.572 m** gap between the near slalom-exit
  buoy and channel entrance boundary provides weak distance evidence. There is
  no preferred inter-task angle.
- Gate width is unspecified. The simulator's estimated 4 m pair is not a profile
  requirement. Gate compactness is only a weak ranking preference.
- Any number of typed towers may support a channel; none are required.

`gcs/app/course_compiler.py` is pure Python, independent of HTTP, telemetry,
browser state, boat commands and numerical packages. It uses the existing local
GPS projection, segment and channel geometry helpers. Input maps are read only.

Distance residuals use `(actual - nominal) / (0.30 * nominal)`. **30% is an
initial development scoring scale, neither a hard placement tolerance nor
measured GPS accuracy.** An unusual measurement means its absolute normalized
residual exceeds one; it remains eligible. The cost is the direct
[Huber definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html):
`0.5*r*r` for `abs(r) <= 1`, otherwise `abs(r)-0.5`.

Slalom costs compare neighboring entrance-center, turn, and exit-center anchors.
Channel costs compare neighboring boundary observations, measured widths and
chain lengths. Local heading changes have weight 0.15; compact gate width has
weight 0.08 relative to slalom spacing. Tower support is a capped 0.15 proximity
cost using the best supporting tower, without imposing a detection count or a
sensor coverage claim. The connection Huber cost has weight 0.05. No global
translation, rotation, straight axis, uniform spacing or right-angle fit is used.
Curves, stagger, skew and arbitrary task connections remain valid inputs.

The compiler runs best-first searches over color-compatible task-role prefixes,
then best-first search over joint interpretations. Joint assignments forbid
reuse except for the explicit gate/slalom entrance alias. Invalid/crossing
channel polygons and sections, degenerate openings/progression, self-crossing
slalom progress and incompatible hints are rejected. Task candidate pools are
bounded at 80; all retained combinations are checked for shared-object conflicts.
An unresolved task has a development ranking cost of 8, allowing partial task
interpretations to outrank a poor forced fit. Incomplete role prefixes are also
reported for diagnosis; they cannot be accepted as complete task templates.

Each request is capped at **5 seconds and 200,000 expanded states**. Fair task
budgets reserve effort for other tasks and joint selection. Pool limits, task
budgets, overall time/states and the five-interpretation limit are reported in
`limits`, separately from finding no proposal. These are bounded heuristic
searches: truncation may exclude the intended interpretation. No result asserts
uniqueness or optimality, even when its cost is small. Gate detail repeats the
entrance measurements for inspection; its alias is counted once in Slalom cost. Operator hints help resolve
ambiguous geometry; there is no calibrated confidence or automatic acceptance.

## Session APIs and invalidation

Use `X-Planner-Session` from `POST /api/session`. Mutations require the current
workspace `revision`; stale requests are rejected.

| Endpoint | Behavior |
| --- | --- |
| `PUT /api/workspace` | Save map edits or normal builder/settings inputs |
| `POST /api/map/history` | `{revision, direction: "undo" or "redo"}` |
| `PUT /api/course/hints` | `{revision, hints: {role: observation_id}}` |
| `POST /api/course/compile` | `{revision}`; return workspace with proposals |
| `POST /api/course/select` | `{revision, task, candidate_id}`; accept a proposed task |
| `POST /api/course/select` | `{revision, task}` accepts a restored task after review; `clear: true` clears it |
| `GET /api/course/file` | Export versioned observation/assignment JSON |
| `POST /api/import` | `{revision, content, format}`; also recognizes course JSON |
| `POST /api/course/prepare` | Use an accepted template, otherwise existing manual/label setup |

Results bind to the exact cleaned map, profile identity/version and hints. Compile
publication additionally checks the session revision and interruption epoch.
Edits/import/reset or Stop during a compile cannot publish delayed results.
Disconnected compile requests discard their result. Map edits clear compilation,
selected templates, routes, approvals, shared-crossing confirmation and map/task
review. Invalidated hints to removed/retyped objects are removed. Hint changes
clear recognition and dependent review/routes. Recompiling clears previous
selected templates so new proposals receive fresh acceptance.

Settings edits invalidate routes/approval while preserving completed recognition
and assignments when map/profile/hints are unchanged. Concurrent settings edits
still supersede an in-flight compilation. Stop discards compilation and marks
selected templates for review; it cannot restore route authority. Browser reload,
new session and backend restart remain empty unless the operator imports a file.

## Course JSON

**Download course JSON** saves this envelope (no generated route, approvals,
execution progress, live vehicle state, settings or run sequence):

```json
{
  "format": "maritime-reviewed-course",
  "version": 1,
  "profile": {"id": "aimm-course-concepts", "version": 1},
  "original_observations": {"schema_version": 3, "...": "original map"},
  "cleaned_map": {"schema_version": 3, "...": "reviewed map"},
  "hints": {"slalom.turn.1": "point_6"},
  "selected_assignments": {
    "gate": {"slalom.entrance.red": "point_2", "slalom.entrance.green": "point_3"}
  }
}
```

Import validates profile/version, map geometry, all role references and colors,
unique compatible use, gate aliasing and channel geometry. Unknown profile/file
versions are rejected. Restored assignments have geometry visible on Map but require fresh confirmation.
Review the map, choose **Review existing assignments**, and **Confirm** each task
to use it. Card geometry/finish review, route generation and all execution steps
must be performed again. Reimport restores neither undo
history nor any prior confirmation. Original observations survive repeated
cleanup/save/reload independently of the cleaned map.

## Validation and limits

Fixtures use the full competition map and cover shuffled rows/replaced IDs,
rotation, curved/staggered slalom, skewed gates, bending/varying-width channel,
non-right-angle connections, competing patterns, extras, missing detections,
unknown types, conflicting pins, invalid channels and bounded-search reporting.
Session/API checks cover undo/redo/additions, original preservation, settings
invalidation, file round trips/rejected references and delayed compilation after
edits/reset/settings/hints/Stop. Compiled opaque-ID GPS assignments for all three
tasks reach Generate → Validate without changing observation positions or chosen
clearance. Frontend checks include finite Leaflet preview geometry and rendered
cleanup, ranked review and restored-assignment controls.

Chrome preview exercises the unlabeled full map, classification, corrections,
remove/undo/redo/addition, overlay, alternatives, hints, acceptance, actual JSON
download/reimport and a reviewed Gate Generate → Validate at 0.5 m/s and 1.8 m
required/preferred buffers. It sends no boat commands. Raw test output, downloaded
course and screenshots are under ignored `simulation/logs/map-compiling/`.
Recognition is not navigation clearance, measured survey robustness, physical
boat/radio acceptance or a guarantee that all ambiguous courses are recognized.

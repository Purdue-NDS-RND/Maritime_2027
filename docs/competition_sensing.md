# AIMM ICC competition context for sensing

Last checked: 2026-11-01. Historical documents guide engineering; current event rules
and organizer clarification govern actual scoring. Recheck before hardware/design freeze.

## Event and sources

The official site lists April 16-17, 2027 at Pokagon State Park, Indiana, and the participant
page lists the competition on April 17 and technical report submission on April 2.
The current rules page still links the older brief/course documents reviewed below.
That linkage does not prove every historical scoring detail is final for 2027.

| Source | Review coverage | Relevant information |
| --- | --- | --- |
| 2025 AIMM Challenge Brief.pdf, 11 pages | Extracted text and rendered pages | Nine mission concepts and headline points; narrative motivator |
| AIMM-ICC Competition Course Details 12-13 2025.pdf, 15 pages | Extracted text and rendered diagrams | Course sketch, navigation-side diagrams, task objects and deployment rules |
| Challenge Competition Scoresheet_4-3-2025.pdf, 2 pages | Text and rendered sheet | Detailed scoring/bonuses, one-hour run and intervention entries |
| Buoy Images _ AIMM ICC.pdf, 4 image-only pages | All pages rendered and inspected | Real fender appearances, reflections, outdoor/pool imagery |
| Official AIMM site and participant information | Browsed 2026-11-01 | Event dates and context |
| Official Rules and Regulations page | Browsed 2026-11-01 | Current vessel/UAV rules, autonomy language and document links |

## Sensing products by mission

Historical task numbering follows the course PDF, not the inconsistent current rule label.

| Mission | Needed scene knowledge | Perception contribution / boundary |
| --- | --- | --- |
| 1 Gate | Red/green pair, approach/passage direction, clearance | Survey both instances; GCS assigns role/color; evaluate entire hull passage |
| 2 Dodge | Ordered turn buoys, pass sides and gates | Accurate complete map plus operator sequencing; detector does not decide route |
| 3 Evade | Channel buoys, detector locations and coverage assumptions | Map relevant obstacles; detector avoidance requires separate coverage/rule information |
| 4 Identify | Selected color among blue/orange/purple/yellow buoys | GCS can label map; local boat identification/contact alignment may be needed |
| 5 Deploy | White buoy with black spiral tape, water-centre position | Local recognition/range; sensor initially within 6 ft (1.8288 m) radius per historical PDF |
| 6 Launch | Black recommended launch-area buoy and actual floating launch target | Boat target bearing/range/geometry; marker location alone is insufficient |
| 7 Recover | Floating protective case and pickup geometry | Detect/map case; local boat approach/range; retrieval mechanism separate |
| 8 Receive | Deployed sensor and base communications | Primarily communications/validation; not a reason to expand aerial CV automatically |
| 9 Return | Marked return buoy/dock approach | Survey/reference plus optional local final approach; navigation/control separate |

The historical navigation diagram instructs passing to the right side of a green buoy
and left side of a red buoy, relative to course travel. Preserve explicit direction/pass-side
roles; do not translate screen-left/right into a route without course heading.
The course sketch is a rough layout, not a surveyed geodetic ground-truth map.

The brief headline points and detailed scoresheet differ. The detailed sheet includes
autonomy, GPS-agnostic and IR/radar bonuses and human remote intervention deductions.
The initial RTK/GPS workflow does not aim for the GPS-agnostic bonus. No score prediction
is made here, and manual labeling does not automatically establish or defeat autonomy.

## Operational implications and questions to resolve

1. Confirm whether post-survey human color/role labeling, position correction and manual
   route preparation are allowed and how they affect autonomous-task scoring.
   Current rules award autonomy bonuses and partial points when human/remote intervention
   is required; their application to pre-execution GCS review needs clarification.
2. Current rules name primary-vessel Slalom (#1) and Evade (#3) requirements, whereas the
   course PDF numbers Gate as #1 and Dodge as #2. Confirm mandatory-task interpretation.
3. Historical course details require drone launch/landing from the LPV and prohibit dock,
   shore or DNR-property operations and catching by a person. Current rules permit a
   specified competition target or primary LPV as landing locations, require initial
   coupling/touching, and prohibit launches from dock/DNR property. Resolve the exact
   approved launch/recovery workflow before demonstrations.
4. Confirm calibration/setup expectations while tethered, communications coverage and
   behavior if drone recovery fails. Launch/recovery is flight/operations ownership.
5. Confirm whether the mapping flight and review count inside the historical one-hour
   scoring window, whether a resurvey is allowed and any constraints on altitude/area.
6. Obtain actual buoy sizes, waterline/freeboard, tether motion, detector geometry/ranges
   and course changes. Do not train navigation assumptions solely on simulator estimates.
7. Verify current scoring document revision, human-intervention treatment and mandatory
   tasks with organizers rather than reconciling conflicts by assumption.

No organizer message has been sent. These questions are tasks for the team's next
existing organizer discussion.

## Simulator interpretation

The provided Maritime competition scene contains 23 buoy entities and six physical props,
with deliberately estimated dimensions for some gates/targets/detectors/case/docks.
The simulator contains fixed positions and historical ArUco regression assets. They do
not establish real appearance, real buoy drift or detector behavior. The selected slalom
acceptance uses ideal exported truth, not a tested drone map. Survey noise, missed/false
objects, origin/projection offsets and movement need separate integration trials.

## Official references

- [AIMM ICC overview](https://www.trine.edu/innovation-one/aimm/index.aspx)
- [Participant information and dates](https://www.trine.edu/innovation-one/aimm/participant-information.aspx)
- [Rules and linked documents](https://www.trine.edu/innovation-one/aimm/rules.aspx)
- [Historical course PDF](https://www.trine.edu/innovation-one/aimm/documents/AIMM-ICC%20Competition%20Course%20Details%2012-13%202025.pdf)
- [Historical brief PDF](https://www.trine.edu/innovation-one/aimm/documents/2025%20AIMM%20Challenge%20Brief.pdf)
- [Historical scoresheet link](https://www.trine.edu/innovation-one/aimm/documents/Challenge%20Competition%20Scoresheet_4-3-2025.pdf)
- [Buoy imagery page](https://www.trine.edu/innovation-one/aimm/buoy-images.aspx)

Web retrieval of the last two links timed out during review; their attached local PDFs
were reviewed successfully. The linked course and brief had matching titles/page counts;
byte identity with the supplied PDFs was not asserted.


# Maritime 2027 Project Overview

## Purpose of This Document

This document defines the mission and intended outcomes of the Maritime 2027
project. It is the starting point for students, advisors, future contributors,
and AI agents who need to understand what the project is trying to accomplish
before making design or implementation decisions.

This is a mission-level overview. It does not define the system architecture,
select algorithms, describe software, or establish implementation standards.
The architectural direction is maintained separately in the
[High-Level Design](High_Level_Design.md).

## Competition Context

The project is being developed for the Artificial Intelligence Maritime
Maneuver Indiana Collegiate Challenge (AIMM ICC), hosted by Trine University in
partnership with Naval Surface Warfare Center Crane Division. The competition
challenges student teams to develop an autonomous low-profile vessel capable of
completing maritime objectives.

The official rules, course events, and scoring details for the team's 2027
competition cycle have not yet been released. Previous competition material may
help explain the general character of the challenge, but it is not a project
requirement and must not be treated as the final 2027 specification. The
[official AIMM ICC website](https://www.trine.edu/innovation-one/aimm/index.aspx)
is the authoritative source for new competition information.

When the 2027 competition material becomes available, the team must review this
overview and confirm that its mission, assumptions, priorities, and measures of
success still align with the official requirements.

## Project Mission

The mission of Maritime 2027 is to develop a dependable autonomous capability
for understanding and navigating buoy-marked waterways with a competition
low-profile vessel.

The vessel must be able to observe buoys, determine how they define the local
environment, choose a safe and appropriate route, and navigate that route with
minimal risk of collision or human intervention. The resulting capability
should provide a strong foundation for competition activities involving gates,
channels, obstacle fields, designated markers, and other buoy-defined tasks.

The immediate emphasis is not on solving every possible AIMM ICC activity. It
is on building a reliable core capability that can support additional mission
objectives after the official events are known.

## Operational Capability Chain

### Detect

The vessel must reliably observe relevant buoys and separate them from waves,
shoreline features, other vessels, glare, reflections, and background clutter.
Detection must remain useful across representative viewing distances, angles,
lighting conditions, and normal vessel motion.

### Understand

An observation becomes useful only when the vessel can interpret it. The vessel
must determine a buoy's relevant characteristics, approximate location, and
relationship to nearby markers. This understanding should allow the vessel to
recognize navigable structures such as gates, channels, boundaries, and ordered
sequences of buoys.

The vessel must also represent uncertainty. A weak or ambiguous observation
must not be treated as certain simply to continue a mission.

### Plan

The vessel must translate its understanding of the buoy arrangement into a safe
route. The selected route should satisfy the mission objective while accounting
for vessel clearance, navigational constraints, observed obstacles, and the
confidence of the available information.

Planning must support reassessment. If the environment is different from what
was expected, or if new observations invalidate the route, the vessel should be
able to choose a revised course instead of continuing blindly.

### Navigate

The vessel must follow the planned route accurately enough to pass through
gates, travel within marked waterways, maneuver around buoys, and arrive at the
intended destination. Navigation should balance progress with safe clearance
and stable vessel motion rather than pursuing speed at the expense of control.

### Monitor and Recover

Autonomous operation must include continuous awareness of whether the mission
is proceeding as intended. The vessel should recognize missed or uncertain
detections, route deviation, unexpected obstacles, loss of navigational
confidence, and unsuccessful maneuvers.

When safe completion is no longer assured, the vessel should take a deliberate
recovery action. Depending on the situation, that may mean slowing down,
stopping, creating distance from an obstacle, reassessing the scene, replanning,
or yielding control for a safe return.

## Guiding System Assumptions

The project begins with the following mission-level assumptions:

- Two ZED X Mini stereo cameras are the planned primary sources of visual and
  depth information for detecting, distinguishing, locating, and tracking
  buoys.
- GPS will provide global position and progress information for the foreseeable
  future. GPS-independent navigation is not a near-term project objective.
- The competition vessel will use an autopilot flight controller for low-level
  vessel control.
- Buoy sensing will provide the local environmental understanding that GPS
  alone cannot supply.
- A human operator must retain a safe way to intervene when autonomous
  operation cannot continue responsibly.

These assumptions establish the intended operating concept without prescribing
the detailed design. Their interfaces, responsibilities, and interactions will
be defined in the HLD.

## Measures of Success

The project will be considered successful when the vessel can repeatedly:

- Detect and distinguish relevant buoys in representative outdoor water
  conditions.
- Estimate buoy positions and relationships well enough to identify navigable
  space.
- Interpret common buoy arrangements such as gates, channels, and obstacle
  paths.
- Select a safe route that is consistent with the observed arrangement and the
  current mission objective.
- Use GPS-assisted navigation to follow that route with appropriate clearance.
- Pass through or around buoy-defined features without unintended contact.
- Recognize uncertainty, route deviation, or failure and respond with a safe
  recovery behavior.
- Produce consistent results across repeated trials rather than succeeding only
  in a single ideal demonstration.
- Adapt to the official 2027 competition requirements after they are released.

Success should be evaluated through observable mission behavior. A component
working in isolation is useful progress, but it is not equivalent to the vessel
successfully understanding and navigating a buoy-marked course.

## Scope Boundaries

This overview intentionally does not define:

- Detailed system architecture or component interfaces.
- Software, communication layers, data formats, or repository organization.
- Specific perception, planning, localization, or control algorithms.
- Mechanical vessel design, propulsion changes, or payload mechanisms.
- Detailed solutions for competition activities unrelated to the core
  buoy-navigation mission.
- GPS-independent navigation as a near-term objective.
- Final acceptance thresholds before the 2027 rules and course details are
  available.

These topics may become important, but they require their own requirements and
design work. The [HLD](High_Level_Design.md) translates this mission into system
boundaries, responsibilities, information flow, failure handling, and
verification plans.

## Guidance for Future Work

Human contributors and AI agents should use this document to evaluate whether
proposed work advances the core mission. Work should strengthen at least one
part of the detect, understand, plan, navigate, monitor, and recover chain
without undermining the safety or reliability of the whole mission.

This overview is not permission to infer missing technical decisions. When a
design choice is not stated here or in an approved HLD, it remains an open
decision. Previous competition material and experimental project artifacts may
inform discussion, but neither automatically defines the desired final system.

The project should favor measurable, repeatable progress toward autonomous
course completion. New capabilities should ultimately be judged by how well
they help the vessel interpret and safely navigate the real buoy-marked
environment presented by AIMM ICC.

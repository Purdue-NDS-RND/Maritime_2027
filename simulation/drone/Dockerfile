ARG BASE_IMAGE=maritime-sim:latest
FROM ${BASE_IMAGE}
USER root
RUN test "$(git -c safe.directory='*' -C /opt/ardupilot rev-parse HEAD)" = 1511f27194f1dcc3728270883047bdf022b3fd53 \
 && test "$(git -c safe.directory='*' -C /opt/ardupilot_gazebo rev-parse HEAD)" = 082a0fe231f6e63bc8d1598f1cba461d9e2ea7f5 \
 && (python3 -c 'from cv2 import aruco' || \
     (apt-get update && apt-get install -y --no-install-recommends python3-opencv && rm -rf /var/lib/apt/lists/*))

USER builder
WORKDIR /opt/ardupilot
RUN HOME=/home/builder ./waf build --target bin/arducopter -j4

USER root
WORKDIR /sim
COPY drone /opt/drone
COPY scenarios/competition.json /opt/drone/competition.json
COPY scripts/competition_scene.py /opt/drone/competition_scene.py
ENV GZ_PARTITION=maritime_drone_sitl \
    GZ_SIM_RESOURCE_PATH=/opt/drone:/opt/ardupilot_gazebo/models
RUN python3 /opt/drone/render_course.py /opt/ardupilot_gazebo/models/iris_with_standoffs/model.sdf \
 && SDF_PATH=/opt/ardupilot_gazebo/models gz sdf -k /opt/drone/iris_competition.sdf

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/drone/start.sh"]
HEALTHCHECK --interval=2s --timeout=2s --retries=4 --start-period=60s CMD test -f /tmp/drone-ready

ARG MARITIME_SOURCE_REVISION=unknown
ARG MARITIME_SOURCE_BRANCH=unknown
ARG MARITIME_SOURCE_DIRTY=unknown
LABEL org.opencontainers.image.revision="${MARITIME_SOURCE_REVISION}" \
      io.maritime.source.branch="${MARITIME_SOURCE_BRANCH}" \
      io.maritime.source.dirty="${MARITIME_SOURCE_DIRTY}"

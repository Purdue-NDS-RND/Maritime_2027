ARG BASE_IMAGE=maritime-sim:latest
FROM ${BASE_IMAGE}
USER root
RUN test "$(git -c safe.directory='*' -C /opt/ardupilot rev-parse HEAD)" = 1511f27194f1dcc3728270883047bdf022b3fd53 \
 && test "$(git -c safe.directory='*' -C /opt/ardupilot_gazebo rev-parse HEAD)" = 082a0fe231f6e63bc8d1598f1cba461d9e2ea7f5 \
 && test "$(git -c safe.directory='*' -C /opt/SITL_Models rev-parse HEAD)" = 25bc38ed8c6c0345840159a8cbc0b02781d52f3c \
 && git -c safe.directory='*' -C /opt/SITL_Models sparse-checkout add Gazebo/models/wildthumper \
 && test -f /opt/SITL_Models/Gazebo/models/wildthumper/model.sdf
COPY rover /opt/rover
ENV GZ_PARTITION=maritime_rover_sitl \
    GZ_SIM_RESOURCE_PATH=/opt/SITL_Models/Gazebo/models:/opt/rover \
    HOME=/sim/state
WORKDIR /sim
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "/opt/rover/start.py"]
HEALTHCHECK --interval=5s --timeout=8s --start-period=90s CMD python3 /opt/rover/probe.py

# Stamp the source used by this build; upstream dependency pins remain separate.
ARG MARITIME_SOURCE_REVISION=unknown
ARG MARITIME_SOURCE_BRANCH=unknown
ARG MARITIME_SOURCE_DIRTY=unknown
LABEL org.opencontainers.image.revision="${MARITIME_SOURCE_REVISION}" \
      io.maritime.source.branch="${MARITIME_SOURCE_BRANCH}" \
      io.maritime.source.dirty="${MARITIME_SOURCE_DIRTY}"

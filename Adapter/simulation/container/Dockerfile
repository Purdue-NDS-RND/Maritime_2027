FROM ros:jazzy-ros-base-noble@sha256:386d06ec6d4188f731bae5678e07b4cb64a4e4d4152090c0bd1f881dcf7706f5

LABEL org.opencontainers.image.title="Maritime Simulation Adapter" \
      maritime.contract.mavros="maritime.mavros_adapter@2.0.0" \
      maritime.contract.camera="maritime.camera_adapter@1.0.0" \
      maritime.ros.base-digest="sha256:386d06ec6d4188f731bae5678e07b4cb64a4e4d4152090c0bd1f881dcf7706f5" \
      maritime.mavros.debian-version="2.15.1-1noble.20260903.022619" \
      maritime.mavros-extras.debian-version="2.15.1-1noble.20260903.025450"

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        geographiclib-tools \
        ros-jazzy-mavros=2.15.1-1noble.20260903.022619 \
        ros-jazzy-mavros-extras=2.15.1-1noble.20260903.025450 \
        ros-jazzy-ros-gz-bridge \
        ros-jazzy-tf2-ros \
    && /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh \
    && test -s /usr/share/GeographicLib/geoids/egm96-5.pgm \
    && dpkg-query -W -f='${Version}\n' ros-jazzy-mavros \
       | grep -Fx '2.15.1-1noble.20260903.022619' \
    && dpkg-query -W -f='${Version}\n' ros-jazzy-mavros-extras \
       | grep -Fx '2.15.1-1noble.20260903.025450' \
    && rm -rf /var/lib/apt/lists/*

COPY ros_ws/src /opt/blueboat_ws/src
RUN source /opt/ros/jazzy/setup.bash \
    && cd /opt/blueboat_ws \
    && colcon build --symlink-install \
    && dpkg-query -W ros-jazzy-ros-gz-bridge \
    && printf '%s\n' \
       'source /opt/ros/jazzy/setup.bash' \
       'source /opt/blueboat_ws/install/setup.bash' \
       > /etc/blueboat_ros_setup.bash

ENV ROS_DOMAIN_ID=0 \
    GZ_PARTITION=ardupilot_blueboat_starter \
    CAMERA_ENABLED=1 \
    FCU_URL=udp://:14552@ \
    SCENARIO_MANIFEST=/scenario/active.manifest.json

CMD ["bash", "-lc", "source /etc/blueboat_ros_setup.bash && exec ros2 launch blueboat_sim_bringup bringup.launch.py"]

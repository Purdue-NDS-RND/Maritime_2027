FROM ros:jazzy-ros-base-noble

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-opencv \
        ros-jazzy-cv-bridge \
        ros-jazzy-mavros-msgs \
        ros-jazzy-message-filters \
        ros-jazzy-ros-gz-bridge \
        ros-jazzy-tf2-ros \
    && python3 -c "import cv2; assert hasattr(cv2, 'aruco')" \
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
    SCENARIO_MANIFEST=/scenario/active.manifest.json

CMD ["bash", "-lc", "source /etc/blueboat_ros_setup.bash && exec ros2 launch blueboat_sim_bringup bringup.launch.py"]

FROM ros:jazzy-ros-base-noble

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        geographiclib-tools wget ros-jazzy-mavros ros-jazzy-mavros-extras \
    && /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh \
    && rm -rf /var/lib/apt/lists/*

COPY ros_ws/src /opt/autonomy_ws/src
RUN source /opt/ros/jazzy/setup.bash \
    && cd /opt/autonomy_ws \
    && colcon build --symlink-install \
    && printf '%s\n' \
       'source /opt/ros/jazzy/setup.bash' \
       'source /opt/autonomy_ws/install/setup.bash' \
       > /etc/maritime_autonomy_setup.bash

ENV ROS_DOMAIN_ID=0
CMD ["bash", "-lc", "source /etc/maritime_autonomy_setup.bash && exec ros2 launch maritime_bringup vehicle.launch.py"]

FROM ros:jazzy-ros-base-noble

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-opencv \
        python3-scipy \
        ros-jazzy-visualization-msgs \
        ros-jazzy-diagnostic-msgs \
        ros-jazzy-cv-bridge \
        ros-jazzy-vision-msgs \
        ros-jazzy-tf2-ros-py \
        ros-jazzy-rosidl-default-generators \
        ros-jazzy-nav2-planner \
        ros-jazzy-nav2-controller \
        ros-jazzy-nav2-bt-navigator \
        ros-jazzy-nav2-lifecycle-manager \
        ros-jazzy-nav2-smac-planner \
        ros-jazzy-nav2-regulated-pure-pursuit-controller \
    && python3 -c "import cv2; assert hasattr(cv2.aruco, 'detectMarkers')" \
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
CMD ["bash", "-lc", "source /etc/maritime_autonomy_setup.bash && exec ros2 run maritime_bringup preimplementation_placeholder"]

FROM ros:jazzy-ros-base-noble

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

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

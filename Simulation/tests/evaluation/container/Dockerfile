FROM ros:jazzy-ros-base-noble@sha256:386d06ec6d4188f731bae5678e07b4cb64a4e4d4152090c0bd1f881dcf7706f5

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-opencv \
        ros-jazzy-cv-bridge \
        ros-jazzy-mavros-msgs \
        ros-jazzy-tf2-ros \
    && python3 -c "import cv2; assert hasattr(cv2, 'aruco')" \
    && rm -rf /var/lib/apt/lists/*

COPY ros_ws/src /opt/evaluation_ws/src
RUN source /opt/ros/jazzy/setup.bash \
    && cd /opt/evaluation_ws \
    && colcon build --symlink-install \
    && printf '%s\n' 'source /opt/ros/jazzy/setup.bash' 'source /opt/evaluation_ws/install/setup.bash' \
       > /etc/blueboat_evaluation_setup.bash

ENV ROS_DOMAIN_ID=0 \
    ADAPTER_ENVIRONMENT=simulation \
    SIMULATION_EVALUATION=0 \
    SCENARIO_MANIFEST=/scenario/active.manifest.json

ENTRYPOINT ["bash", "-lc", "source /etc/blueboat_evaluation_setup.bash && exec \"$@\"", "--"]
CMD ["ros2", "run", "blueboat_sim_evaluation", "evaluation", "--help"]

FROM ros:jazzy-ros-base-noble@sha256:386d06ec6d4188f731bae5678e07b4cb64a4e4d4152090c0bd1f881dcf7706f5

ARG DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ros-jazzy-rviz2 \
        ros-jazzy-rqt-graph \
        ros-jazzy-tf2-tools \
        ros-jazzy-tf2-ros \
        ros-jazzy-rmw-fastrtps-cpp \
        ros-jazzy-rosbag2 \
        ros-jazzy-mavros-msgs \
        libgl1-mesa-dri \
    && rm -rf /var/lib/apt/lists/*

COPY container/entrypoint.sh /usr/local/bin/monitor-entrypoint
COPY container/bashrc /etc/monitor.bashrc
COPY config /opt/monitor/config
ENV HOME=/tmp/monitor-home \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    FASTRTPS_DEFAULT_PROFILES_FILE=/opt/monitor/config/fastdds.xml
ENTRYPOINT ["/usr/local/bin/monitor-entrypoint"]
CMD ["bash", "--rcfile", "/etc/monitor.bashrc", "-i"]

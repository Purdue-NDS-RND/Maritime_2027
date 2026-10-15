FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG ARDUPILOT_VERSION=Rover-4.7.0
ARG ARDUPILOT_COMMIT=1511f27194f1dcc3728270883047bdf022b3fd53
ARG ARDUPILOT_GAZEBO_COMMIT=082a0fe231f6e63bc8d1598f1cba461d9e2ea7f5
ARG SITL_MODELS_COMMIT=25bc38ed8c6c0345840159a8cbc0b02781d52f3c
ARG ASV_WAVE_SIM_COMMIT=ca8629df4e191235753dfae92ef725d30b923364

LABEL org.opencontainers.image.title="ArduPilot BlueBoat Starter" \
      org.opencontainers.image.description="ArduPilot Rover SITL with BlueBoat, Gazebo Harmonic, and wave hydrodynamics" \
      org.opencontainers.image.version="${ARDUPILOT_VERSION}" \
      io.ardupilot.commit="${ARDUPILOT_COMMIT}" \
      io.ardupilot.gazebo.commit="${ARDUPILOT_GAZEBO_COMMIT}" \
      io.ardupilot.sitl-models.commit="${SITL_MODELS_COMMIT}" \
      io.asv-wave-sim.commit="${ASV_WAVE_SIM_COMMIT}"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Gazebo Harmonic is installed from OSRF's Jammy repository. All simulator
# dependencies stay inside this image; the Ubuntu 24.04 host only needs Docker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        sudo \
    && curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
        -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main" \
        > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ccache \
        cmake \
        gawk \
        git \
        gz-harmonic \
        gstreamer1.0-gl \
        gstreamer1.0-libav \
        gstreamer1.0-plugins-bad \
        libcgal-dev \
        libeigen3-dev \
        libfftw3-dev \
        libgl1-mesa-dri \
        libglx-mesa0 \
        libgstreamer-plugins-base1.0-dev \
        libgstreamer1.0-dev \
        libgz-sim8-dev \
        libopencv-dev \
        libtool \
        libxml2-dev \
        libxslt1-dev \
        mesa-utils \
        ppp \
        procps \
        python-is-python3 \
        python3-dev \
        python3-numpy \
        python3-pexpect \
        python3-pip \
        python3-psutil \
        python3-pyparsing \
        python3-setuptools \
        rapidjson-dev \
        tini \
        wget \
    && useradd --create-home --shell /bin/bash --uid 10001 builder \
    && usermod -aG sudo builder \
    && printf 'builder ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/builder \
    && chmod 0440 /etc/sudoers.d/builder \
    && mkdir -p /opt/ardupilot /opt/ardupilot-python \
    && chown builder:builder /opt/ardupilot /opt/ardupilot-python

ENV PYTHONUSERBASE=/opt/ardupilot-python
ENV PATH=/opt/ardupilot-python/bin:/opt/ardupilot/Tools/autotest:${PATH}

USER builder
WORKDIR /opt

# Clone the named stable release and prove it resolves to the expected commit.
RUN git clone --depth 1 --branch "${ARDUPILOT_VERSION}" --recurse-submodules \
        --shallow-submodules https://github.com/ArduPilot/ardupilot.git /opt/ardupilot \
    && test "$(git -C /opt/ardupilot rev-parse HEAD)" = "${ARDUPILOT_COMMIT}"

RUN python3 -m pip install --user --no-cache-dir --upgrade \
        pip packaging setuptools wheel \
    && python3 -m pip install --user --no-cache-dir \
        future \
        lxml \
        pymavlink \
        pyserial \
        MAVProxy \
        geocoder \
        'empy==3.3.4' \
        ptyprocess \
        dronecan \
        tabulate

RUN cd /opt/ardupilot \
    && ./waf configure --board sitl \
    && ./waf build --target bin/ardurover

USER root
WORKDIR /opt

# The official Gazebo bridge has no stable release tag, so use an immutable SHA.
RUN git init /opt/ardupilot_gazebo \
    && git -C /opt/ardupilot_gazebo remote add origin https://github.com/ArduPilot/ardupilot_gazebo.git \
    && git -C /opt/ardupilot_gazebo fetch --depth 1 origin "${ARDUPILOT_GAZEBO_COMMIT}" \
    && git -C /opt/ardupilot_gazebo checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/ardupilot_gazebo rev-parse HEAD)" = "${ARDUPILOT_GAZEBO_COMMIT}" \
    && cmake -S /opt/ardupilot_gazebo -B /opt/ardupilot_gazebo/build \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    && cmake --build /opt/ardupilot_gazebo/build --parallel "$(nproc)"

# Fetch only the official BlueBoat model from the large SITL model repository.
RUN git init /opt/SITL_Models \
    && git -C /opt/SITL_Models remote add origin https://github.com/ArduPilot/SITL_Models.git \
    && git -C /opt/SITL_Models sparse-checkout init --cone \
    && git -C /opt/SITL_Models sparse-checkout set Gazebo/models/blueboat \
    && git -C /opt/SITL_Models fetch --depth 1 --filter=blob:none origin "${SITL_MODELS_COMMIT}" \
    && git -C /opt/SITL_Models checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/SITL_Models rev-parse HEAD)" = "${SITL_MODELS_COMMIT}" \
    && test -f /opt/SITL_Models/Gazebo/models/blueboat/model.sdf

# ASV Wave Sim's pinned gnuplot-iostream helper configures these Boost
# components even when its plotting tests are disabled.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libboost-filesystem-dev \
        libboost-iostreams-dev \
        libboost-system-dev \
    && rm -rf /var/lib/apt/lists/*

# Build the ROS-independent Gazebo Harmonic wave and hydrodynamics systems.
RUN git init /opt/asv_wave_sim \
    && git -C /opt/asv_wave_sim remote add origin https://github.com/srmainwaring/asv_wave_sim.git \
    && git -C /opt/asv_wave_sim fetch --depth 1 origin "${ASV_WAVE_SIM_COMMIT}" \
    && git -C /opt/asv_wave_sim checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/asv_wave_sim rev-parse HEAD)" = "${ASV_WAVE_SIM_COMMIT}" \
    && GZ_VERSION=harmonic cmake \
        -S /opt/asv_wave_sim/gz-waves \
        -B /opt/asv_wave_sim/build \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DCMAKE_INSTALL_PREFIX=/opt/asv_wave_sim/install \
        -DCMAKE_INSTALL_LIBDIR=lib \
        -DBUILD_TESTING=OFF \
    && cmake --build /opt/asv_wave_sim/build --parallel "$(nproc)" \
    && cmake --install /opt/asv_wave_sim/build \
    && test -f /opt/asv_wave_sim/install/lib/libgz-waves1-hydrodynamics-system.so \
    && test -f /opt/asv_wave_sim/install/lib/libgz-waves1-waves-model-system.so

RUN apt-get update \
    && apt-get install -y --no-install-recommends libdebuginfod1 libqt5svg5 \
    && rm /etc/sudoers.d/builder \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete

COPY --chmod=0755 container/start-sim.sh /usr/local/bin/start-sim.sh
COPY --chmod=0755 container/sitl-process-wrapper.sh /usr/local/bin/sitl-process-wrapper.sh
COPY --chmod=0755 container/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY config /opt/boat_sim/config
COPY worlds /opt/boat_sim/worlds
COPY models /opt/boat_sim/models
COPY plugins /opt/boat_sim/plugins
RUN cmake -S /opt/boat_sim/plugins -B /opt/boat_sim/plugins/build \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=/opt/boat_sim \
    && cmake --build /opt/boat_sim/plugins/build --parallel "$(nproc)" \
    && cmake --install /opt/boat_sim/plugins/build
COPY scenarios /opt/boat_sim/scenarios
COPY --chmod=0755 scripts /opt/boat_sim/scripts
COPY --chmod=0755 scripts/smoke-test.py /opt/boat_sim/scripts/smoke-test.py

RUN python3 /opt/boat_sim/scripts/augment_blueboat_model.py \
      --source /opt/SITL_Models/Gazebo/models/blueboat/model.sdf \
      --payload /opt/boat_sim/models/blueboat_rgbd/camera_payload.sdf \
      --output /opt/boat_sim/models/blueboat_rgbd/model.sdf \
      --expected-sha256 fc651a9d4aff258fe675d94aeb24b91d82439cc441f99b00f921e316fbc3de57

ENV GZ_VERSION=harmonic \
    GZ_PARTITION=ardupilot_blueboat_starter \
    LD_LIBRARY_PATH=/opt/asv_wave_sim/install/lib \
    GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/boat_sim/lib:/opt/ardupilot_gazebo/build:/opt/asv_wave_sim/install/lib \
    GZ_SIM_RESOURCE_PATH=/sim/generated-worlds:/opt/boat_sim/worlds:/opt/boat_sim/models:/opt/SITL_Models/Gazebo/models:/opt/ardupilot_gazebo/models:/opt/ardupilot_gazebo/worlds:/opt/asv_wave_sim/gz-waves-models/models:/opt/asv_wave_sim/gz-waves-models/world_models:/opt/asv_wave_sim/gz-waves-models/worlds \
    HOME=/sim/state \
    LOG_DIR=/sim \
    WORLD=blueboat_waves.sdf \
    MAVLINK_QGC=udp:127.0.0.1:14550 \
    MAVLINK_API=udp:127.0.0.1:14551 \
    MAVLINK_MAVROS=udp:127.0.0.1:14552 \
    ENABLE_MAVROS=0 \
    CAMERA_ENABLED=0 \
    SOFTWARE_RENDERING=0 \
    WIPE_PARAMS=0 \
    QT_X11_NO_MITSHM=1

WORKDIR /sim
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/start-sim.sh"]

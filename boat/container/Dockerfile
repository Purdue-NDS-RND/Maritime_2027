FROM ros:jazzy-ros-base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-colcon-common-extensions python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/boat-venv \
    && /opt/boat-venv/bin/pip install --no-cache-dir pymavlink==2.4.50
ENV PATH=/opt/boat-venv/bin:$PATH
ENV PYTHONPATH=/opt/boat-venv/lib/python3.12/site-packages
COPY . /ws/src/boat_app
WORKDIR /ws
RUN source /opt/ros/jazzy/setup.bash \
    && colcon build --packages-select boat_app --event-handlers console_direct+ \
        --cmake-args -DPython3_EXECUTABLE=/opt/boat-venv/bin/python3
COPY --chmod=0755 container/entrypoint.sh /boat-entrypoint.sh
ENTRYPOINT ["/boat-entrypoint.sh"]
CMD ["python3", "-m", "boat_app.node"]

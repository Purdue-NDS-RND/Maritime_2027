# Offline bag tooling stays out of the autonomy runtime image.
FROM maritime-autonomy:jazzy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ros-jazzy-rosbag2 python3-yaml \
    && rm -rf /var/lib/apt/lists/*

COPY runner.py /opt/benchmark/runner.py
ENTRYPOINT ["bash", "-c", "source /etc/maritime_autonomy_setup.bash && exec python3 /opt/benchmark/runner.py \"$@\"", "--"]
CMD ["--help"]

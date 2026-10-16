# Playback, result recording, and plotting stay out of the autonomy image.
FROM maritime-autonomy:jazzy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ros-jazzy-rosbag2 python3-yaml python3-matplotlib \
    && rm -rf /var/lib/apt/lists/*

COPY *.py /opt/benchmark/
ENTRYPOINT ["bash", "-c", "source /etc/maritime_autonomy_setup.bash && exec python3 /opt/benchmark/pipeline.py \"$@\"", "--"]
CMD ["--help"]

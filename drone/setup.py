from setuptools import find_packages, setup

setup(
    name="maritime_perception", version="0.1.0", python_requires=">=3.11",
    packages=find_packages(),
    package_data={"maritime_perception": ["schemas/*.json"],
                  "perception_synthetic": ["scenarios/*.json"]},
    install_requires=[line.strip() for line in open("requirements.txt") if line.strip()],
    data_files=[("share/ament_index/resource_index/packages", ["resource/maritime_perception"]),
                ("share/maritime_perception", ["package.xml"]),
                ("share/maritime_perception/launch", ["launch/replay.launch.py"])],
    entry_points={"console_scripts": ["perception_replay=maritime_perception.replay:main",
                                      "perception_ros=maritime_perception.adapters.ros_node:main",
                                      "perception_imu=maritime_perception.adapters.imu_listener:main"]},
    maintainer="Maritime", maintainer_email="maintainer@example.com",
    description="Input-independent aerial object geolocation and uncertainty",
    license="Proprietary",
)

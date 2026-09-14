from setuptools import find_packages, setup

package_name = "blueboat_sim_evaluation"
setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="BlueBoat Simulation",
    maintainer_email="maintainer@example.com",
    description="Simulation-only BlueBoat semantic evaluators",
    license="Apache-2.0",
    entry_points={"console_scripts": [
        "evaluation = blueboat_sim_evaluation.cli:main",
        "sensor_smoke = blueboat_sim_evaluation.sensor_smoke:main",
        "mavros_smoke = blueboat_sim_evaluation.mavros_smoke:main",
    ]},
)

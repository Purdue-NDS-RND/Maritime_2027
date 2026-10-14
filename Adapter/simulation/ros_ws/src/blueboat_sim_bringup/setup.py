from glob import glob
from setuptools import find_packages, setup

package_name = "blueboat_sim_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="BlueBoat Simulation",
    maintainer_email="maintainer@example.com",
    description="BlueBoat Simulation Adapter bringup and diagnostics",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "healthcheck = blueboat_sim_bringup.healthcheck:main",
            "diagnostics = blueboat_sim_bringup.diagnostics:main",
            "configure_mavros = blueboat_sim_bringup.configure_mavros:main",
            "readiness = blueboat_sim_bringup.readiness:main",
        ]
    },
)

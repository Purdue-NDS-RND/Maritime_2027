from glob import glob
from setuptools import find_packages, setup

package_name = "maritime_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Maritime 2027",
    maintainer_email="maintainer@example.com",
    description="Shared autonomy bringup and flight-controller connection checks",
    license="Apache-2.0",
    entry_points={"console_scripts": ["healthcheck = maritime_bringup.healthcheck:main"]},
)

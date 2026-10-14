from setuptools import find_packages, setup

package_name = "maritime_bringup"

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
    maintainer="Maritime 2027",
    maintainer_email="maintainer@example.com",
    description="Simulation-only pre-implementation autonomy bootstrap",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "preimplementation_placeholder = maritime_bringup.placeholder:main",
            "placeholder_healthcheck = maritime_bringup.placeholder_healthcheck:main",
        ],
    },
)

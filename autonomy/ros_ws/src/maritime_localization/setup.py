from setuptools import find_packages, setup

setup(
    name="maritime_localization",
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/maritime_localization"]),
        ("share/maritime_localization", ["package.xml"]),
        ("share/maritime_localization/config", ["config/bearing_ekf.yaml"]),
        ("share/maritime_localization/launch", ["launch/pipeline.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Maritime 2027",
    maintainer_email="maintainer@example.com",
    description="Buoy positioning and persistent RGB bearing-only mapping",
    license="Apache-2.0",
    entry_points={"console_scripts": ["buoy_mapper = maritime_localization.mapping_node:main"]},
)

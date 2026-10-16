from setuptools import find_packages, setup

setup(
    name="maritime_localization",
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/maritime_localization"]),
        ("share/maritime_localization", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Maritime 2027",
    maintainer_email="maintainer@example.com",
    description="Buoy positioning interfaces; algorithms are not implemented",
    license="Apache-2.0",
)

from setuptools import setup

setup(
    name="boat_app", version="0.1.0", packages=["boat_app"],
    data_files=[("share/ament_index/resource_index/packages", ["resource/boat_app"]),
                ("share/boat_app", ["package.xml"])],
    install_requires=["setuptools"], zip_safe=True,
    maintainer="Maritime", maintainer_email="maintainer@example.com",
    description="Supplied GPS mission execution through ArduPilot",
    license="Proprietary",
    entry_points={"console_scripts": ["mission = boat_app.node:main"]},
)

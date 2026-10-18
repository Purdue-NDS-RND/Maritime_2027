from glob import glob
from setuptools import setup
setup(name='maritime_navigation', version='0.1.0', packages=['maritime_navigation'],
      data_files=[('share/ament_index/resource_index/packages', ['resource/maritime_navigation']),
                  ('share/maritime_navigation', ['package.xml']),
                  ('share/maritime_navigation/launch', glob('launch/*.py')),
                  ('share/maritime_navigation/config', glob('config/*')),
                  ('share/maritime_navigation/behavior_trees', glob('behavior_trees/*.xml'))],
      entry_points={'console_scripts': ['navigator = maritime_navigation.node:main']})

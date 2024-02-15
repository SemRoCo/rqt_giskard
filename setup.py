from setuptools import setup
from catkin_pkg.python_setup import generate_distutils_setup

d = generate_distutils_setup(
    packages=['rqt_giskard_lib', 'rqt_giskard_lib.plugins', 'rqt_giskard_lib.qt_dotgraph'],
    package_dir={'': 'src'}
)

setup(**d)

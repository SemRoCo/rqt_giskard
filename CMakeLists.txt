cmake_minimum_required(VERSION 3.0.2)
project(rqt_giskard)
set(CMAKE_CXX_FLAGS "-g ${CMAKE_CXX_FLAGS}")
# Load catkin and all dependencies required for this package
find_package(catkin REQUIRED py_trees_msgs rqt_bag)
catkin_package()
catkin_python_setup()

install(FILES plugin.xml
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

install(DIRECTORY resource
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

catkin_install_python(PROGRAMS 
  scripts/rqt_giskard.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})

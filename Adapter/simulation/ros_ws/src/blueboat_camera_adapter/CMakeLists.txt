cmake_minimum_required(VERSION 3.8)
project(blueboat_camera_adapter)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)

add_executable(camera_boundary src/camera_boundary.cpp)
ament_target_dependencies(camera_boundary rclcpp sensor_msgs)
install(TARGETS camera_boundary DESTINATION lib/${PROJECT_NAME})
ament_package()

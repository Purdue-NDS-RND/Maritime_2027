cmake_minimum_required(VERSION 3.8)
project(blueboat_camera_adapter)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(tf2_msgs REQUIRED)

add_executable(camera_boundary src/camera_boundary.cpp)
target_include_directories(camera_boundary PRIVATE include)
ament_target_dependencies(camera_boundary rclcpp diagnostic_msgs sensor_msgs tf2_msgs)
install(TARGETS camera_boundary DESTINATION lib/${PROJECT_NAME})
ament_package()

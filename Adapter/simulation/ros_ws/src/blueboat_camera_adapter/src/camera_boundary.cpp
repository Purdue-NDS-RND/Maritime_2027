#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/camera_info.hpp"
#include "sensor_msgs/msg/image.hpp"

class CameraBoundary final : public rclcpp::Node {
 public:
  CameraBoundary() : Node("camera_0_boundary") {
    const auto qos = rclcpp::SensorDataQoS().keep_last(1);
    color_pub_ = create_publisher<sensor_msgs::msg::Image>(
        "/sensors/camera_0/color/image_raw", qos);
    depth_pub_ = create_publisher<sensor_msgs::msg::Image>(
        "/sensors/camera_0/depth/image_rect_raw", qos);
    info_pub_ = create_publisher<sensor_msgs::msg::CameraInfo>(
        "/sensors/camera_0/color/camera_info", qos);
    color_sub_ = create_subscription<sensor_msgs::msg::Image>(
        "/adapter/private/camera_0/color", qos,
        [this](sensor_msgs::msg::Image::UniquePtr message) {
          if (message->encoding != "rgb8" && message->encoding != "bgr8") {
            RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
                                  "rejecting unsupported color encoding");
            return;
          }
          message->header.frame_id = "camera_0_optical_frame";
          color_pub_->publish(std::move(message));
        });
    depth_sub_ = create_subscription<sensor_msgs::msg::Image>(
        "/adapter/private/camera_0/depth", qos,
        [this](sensor_msgs::msg::Image::UniquePtr message) {
          if (message->encoding != "32FC1" || message->step != message->width * 4U ||
              message->data.size() != static_cast<size_t>(message->step) * message->height) {
            RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
                                  "rejecting non-canonical depth layout");
            return;
          }
          const uint16_t endian_probe = 0x0102;
          const bool host_big_endian =
              *reinterpret_cast<const uint8_t *>(&endian_probe) == 0x01;
          const bool swap = static_cast<bool>(message->is_bigendian) != host_big_endian;
          const float nan = std::numeric_limits<float>::quiet_NaN();
          for (size_t offset = 0; offset < message->data.size(); offset += 4) {
            uint32_t bits;
            std::memcpy(&bits, message->data.data() + offset, sizeof(bits));
            if (swap) bits = __builtin_bswap32(bits);
            float value;
            std::memcpy(&value, &bits, sizeof(value));
            if (!std::isfinite(value) || value <= 0.0F) {
              uint32_t replacement;
              std::memcpy(&replacement, &nan, sizeof(replacement));
              if (swap) replacement = __builtin_bswap32(replacement);
              std::memcpy(message->data.data() + offset, &replacement, sizeof(replacement));
            }
          }
          message->header.frame_id = "camera_0_optical_frame";
          depth_pub_->publish(std::move(message));
        });
    info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
        "/adapter/private/camera_0/camera_info", qos,
        [this](sensor_msgs::msg::CameraInfo::UniquePtr message) {
          message->header.frame_id = "camera_0_optical_frame";
          info_pub_->publish(std::move(message));
        });
  }

 private:
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr color_pub_, depth_pub_;
  rclcpp::Publisher<sensor_msgs::msg::CameraInfo>::SharedPtr info_pub_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr color_sub_, depth_sub_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr info_sub_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CameraBoundary>());
  rclcpp::shutdown();
  return 0;
}

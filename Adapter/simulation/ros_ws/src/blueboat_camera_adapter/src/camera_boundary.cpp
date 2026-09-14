#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/camera_info.hpp"
#include "sensor_msgs/msg/image.hpp"

namespace {
constexpr char kPrivateFrame[] = "zed2i_left_camera_optical_frame";
constexpr char kPublicFrame[] = "camera_0_optical_frame";
constexpr int64_t kMaxAgeNs = 100000000;
constexpr size_t kMaxQueue = 64;

int64_t stamp_ns(const builtin_interfaces::msg::Time & stamp) {
  return static_cast<int64_t>(stamp.sec) * 1000000000LL + stamp.nanosec;
}

template<typename Values>
bool finite_values(const Values & values) {
  return std::all_of(values.begin(), values.end(), [](double value) { return std::isfinite(value); });
}
}  // namespace

class CameraBoundary final : public rclcpp::Node {
 public:
  CameraBoundary() : Node("camera_0_boundary") {
    const auto registration_mode = declare_parameter<std::string>("registration_mode", "");
    const auto registration_evidence = declare_parameter<std::string>("registration_evidence_ref", "");
    if (registration_mode != "color" || registration_evidence != "simulation-rgbd-registration") {
      throw std::runtime_error("camera registration configuration/evidence is not contract-approved");
    }
    const auto qos = rclcpp::SensorDataQoS().keep_last(1);
    color_pub_ = create_publisher<sensor_msgs::msg::Image>("/sensors/camera_0/color/image_raw", qos);
    depth_pub_ = create_publisher<sensor_msgs::msg::Image>("/sensors/camera_0/depth/image_rect_raw", qos);
    info_pub_ = create_publisher<sensor_msgs::msg::CameraInfo>("/sensors/camera_0/color/camera_info", qos);
    color_sub_ = create_subscription<sensor_msgs::msg::Image>(
        "/adapter/private/camera_0/color", qos,
        [this](sensor_msgs::msg::Image::UniquePtr message) { receive_color(std::move(message)); });
    depth_sub_ = create_subscription<sensor_msgs::msg::Image>(
        "/adapter/private/camera_0/depth", qos,
        [this](sensor_msgs::msg::Image::UniquePtr message) { receive_depth(std::move(message)); });
    info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
        "/adapter/private/camera_0/camera_info", qos,
        [this](sensor_msgs::msg::CameraInfo::UniquePtr message) { receive_info(std::move(message)); });
  }

 private:
  bool valid_stamp(int64_t stamp, int64_t & previous, const char * stream) {
    const int64_t now = get_clock()->now().nanoseconds();
    if (stamp <= 0 || stamp <= previous || now <= 0 || stamp > now || now - stamp > kMaxAgeNs) {
      RCLCPP_ERROR(get_logger(), "rejecting %s with invalid/non-fresh stamp", stream);
      return false;
    }
    previous = stamp;
    return true;
  }

  bool valid_color(const sensor_msgs::msg::Image & message) const {
    const bool encoding = message.encoding == "rgb8" || message.encoding == "bgr8";
    return encoding && message.header.frame_id == kPrivateFrame && message.width > 0 &&
           message.height > 0 && message.step == message.width * 3U &&
           message.data.size() == static_cast<size_t>(message.step) * message.height;
  }

  bool valid_depth(const sensor_msgs::msg::Image & message) const {
    return message.encoding == "32FC1" && message.header.frame_id == kPrivateFrame &&
           message.width > 0 && message.height > 0 && message.step == message.width * 4U &&
           message.data.size() == static_cast<size_t>(message.step) * message.height;
  }

  bool valid_info(const sensor_msgs::msg::CameraInfo & message) const {
    size_t expected_d = 0;
    if (message.distortion_model == "plumb_bob") expected_d = 5;
    if (message.distortion_model == "rational_polynomial") expected_d = 8;
    if (message.distortion_model == "equidistant") expected_d = 4;
    return message.header.frame_id == kPrivateFrame && message.width > 0 && message.height > 0 &&
           expected_d != 0 && message.d.size() == expected_d && finite_values(message.d) &&
           finite_values(message.k) && finite_values(message.r) && finite_values(message.p) &&
           message.k[0] > 0 && message.k[4] > 0 && message.k[8] == 1 &&
           message.p[0] > 0 && message.p[5] > 0 && message.p[10] == 1;
  }

  template<typename Queue>
  void bound(Queue & queue, const char * stream) {
    while (queue.size() > kMaxQueue) {
      RCLCPP_ERROR(get_logger(), "%s matching queue overflow; dropping oldest candidate", stream);
      queue.erase(queue.begin());
    }
  }

  void receive_color(sensor_msgs::msg::Image::UniquePtr message) {
    const int64_t stamp = stamp_ns(message->header.stamp);
    if (!valid_stamp(stamp, last_color_stamp_, "color") || !valid_color(*message)) return;
    colors_.emplace(stamp, std::move(message));
    bound(colors_, "color");
    match();
  }

  void receive_depth(sensor_msgs::msg::Image::UniquePtr message) {
    const int64_t stamp = stamp_ns(message->header.stamp);
    if (!valid_stamp(stamp, last_depth_stamp_, "depth") || !valid_depth(*message)) return;
    depths_.emplace(stamp, std::move(message));
    bound(depths_, "depth");
    match();
  }

  void receive_info(sensor_msgs::msg::CameraInfo::UniquePtr message) {
    const int64_t stamp = stamp_ns(message->header.stamp);
    if (!valid_stamp(stamp, last_info_stamp_, "CameraInfo") || !valid_info(*message)) return;
    infos_.emplace(stamp, std::move(message));
    bound(infos_, "CameraInfo");
    match();
  }

  void normalize_depth(sensor_msgs::msg::Image & message) const {
    const uint16_t probe = 0x0102;
    const bool host_big = *reinterpret_cast<const uint8_t *>(&probe) == 0x01;
    const bool swap = static_cast<bool>(message.is_bigendian) != host_big;
    const float nan = std::numeric_limits<float>::quiet_NaN();
    for (size_t offset = 0; offset < message.data.size(); offset += 4) {
      uint32_t bits;
      std::memcpy(&bits, message.data.data() + offset, sizeof(bits));
      if (swap) bits = __builtin_bswap32(bits);
      float value;
      std::memcpy(&value, &bits, sizeof(value));
      if (!std::isfinite(value) || value <= 0.0F) {
        std::memcpy(&bits, &nan, sizeof(bits));
        if (swap) bits = __builtin_bswap32(bits);
        std::memcpy(message.data.data() + offset, &bits, sizeof(bits));
      }
    }
  }

  void expire_before(int64_t stamp) {
    while (!depths_.empty() && depths_.begin()->first < stamp) depths_.erase(depths_.begin());
    while (!infos_.empty() && infos_.begin()->first < stamp) infos_.erase(infos_.begin());
  }

  void match() {
    while (!colors_.empty()) {
      const int64_t stamp = colors_.begin()->first;
      expire_before(stamp);
      auto depth = depths_.find(stamp);
      auto info = infos_.find(stamp);
      if (depth == depths_.end() || info == infos_.end()) {
        const bool depth_advanced = !depths_.empty() && depths_.rbegin()->first > stamp;
        const bool info_advanced = !infos_.empty() && infos_.rbegin()->first > stamp;
        const bool expired = get_clock()->now().nanoseconds() - stamp > kMaxAgeNs;
        if (depth_advanced || info_advanced || expired) {
          RCLCPP_ERROR(get_logger(), "rejecting unmatched color anchor");
          colors_.erase(colors_.begin());
          continue;
        }
        return;
      }
      auto & color_message = *colors_.begin()->second;
      auto & depth_message = *depth->second;
      auto & info_message = *info->second;
      if (color_message.width != depth_message.width || color_message.height != depth_message.height ||
          color_message.width != info_message.width || color_message.height != info_message.height) {
        RCLCPP_ERROR(get_logger(), "rejecting triple with incompatible raster geometry");
      } else {
        // Gazebo's RGBD depth product is registered to color; startup has
        // validated the immutable simulation-rgbd-registration evidence ID.
        normalize_depth(depth_message);
        color_message.header.frame_id = kPublicFrame;
        depth_message.header.frame_id = kPublicFrame;
        info_message.header.frame_id = kPublicFrame;
        color_pub_->publish(color_message);
        depth_pub_->publish(depth_message);
        info_pub_->publish(info_message);
      }
      colors_.erase(colors_.begin());
      depths_.erase(depth);
      infos_.erase(info);
    }
  }

  std::map<int64_t, sensor_msgs::msg::Image::UniquePtr> colors_, depths_;
  std::map<int64_t, sensor_msgs::msg::CameraInfo::UniquePtr> infos_;
  int64_t last_color_stamp_{0}, last_depth_stamp_{0}, last_info_stamp_{0};
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

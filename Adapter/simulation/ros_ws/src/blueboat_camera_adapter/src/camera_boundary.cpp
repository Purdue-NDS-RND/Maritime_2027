#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>

#include "rclcpp/rclcpp.hpp"
#include "diagnostic_msgs/msg/diagnostic_array.hpp"
#include "diagnostic_msgs/msg/diagnostic_status.hpp"
#include "diagnostic_msgs/msg/key_value.hpp"
#include "sensor_msgs/msg/camera_info.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "tf2_msgs/msg/tf_message.hpp"
#include "blueboat_camera_adapter/matching.hpp"
#include "blueboat_camera_adapter/tf_validation.hpp"

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
    diagnostics_pub_ = create_publisher<diagnostic_msgs::msg::DiagnosticArray>("/diagnostics", 10);
    color_sub_ = create_subscription<sensor_msgs::msg::Image>(
        "/adapter/private/camera_0/color", qos,
        [this](sensor_msgs::msg::Image::UniquePtr message) { receive_color(std::move(message)); });
    depth_sub_ = create_subscription<sensor_msgs::msg::Image>(
        "/adapter/private/camera_0/depth", qos,
        [this](sensor_msgs::msg::Image::UniquePtr message) { receive_depth(std::move(message)); });
    info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
        "/adapter/private/camera_0/camera_info", qos,
        [this](sensor_msgs::msg::CameraInfo::UniquePtr message) { receive_info(std::move(message)); });
    tf_sub_ = create_subscription<tf2_msgs::msg::TFMessage>(
        "/tf_static", rclcpp::QoS(10).transient_local().reliable(),
        [this](const tf2_msgs::msg::TFMessage & message) { receive_tf(message); });
    diagnostics_timer_ = create_wall_timer(
        std::chrono::milliseconds(500), [this]() { match(); publish_diagnostics(); });
  }

 private:
  std::string invalid_stamp_reason(int64_t stamp, int64_t previous) {
    const int64_t now = get_clock()->now().nanoseconds();
    if (stamp <= 0 || stamp <= previous) return "nonmonotonic_header_stamp";
    if (now <= 0 || stamp > now) return "future_acquisition_stamp";
    if (now - stamp > kMaxAgeNs) return "acquisition_timeout";
    return "";
  }

  void reject(const std::string & component, const std::string & reason) {
    ++rejected_count_;
    errors_[component] = reason;
    RCLCPP_ERROR(get_logger(), "camera %s rejection: %s", component.c_str(), reason.c_str());
  }

  std::string invalid_color_reason(const sensor_msgs::msg::Image & message) const {
    if (message.header.frame_id != kPrivateFrame) return "frame_mismatch";
    if (message.encoding != "rgb8" && message.encoding != "bgr8") return "unsupported_encoding";
    if (message.width == 0 || message.height == 0) return "invalid_dimensions";
    if (message.step != message.width * 3U ||
        message.data.size() != static_cast<size_t>(message.step) * message.height) {
      return "invalid_data_layout";
    }
    return "";
  }

  std::string invalid_depth_reason(const sensor_msgs::msg::Image & message) const {
    if (message.header.frame_id != kPrivateFrame) return "frame_mismatch";
    if (message.encoding != "32FC1") return "unsupported_encoding";
    if (message.width == 0 || message.height == 0) return "invalid_dimensions";
    if (message.step != message.width * 4U ||
        message.data.size() != static_cast<size_t>(message.step) * message.height) {
      return "invalid_data_layout";
    }
    return "";
  }

  std::string invalid_info_reason(const sensor_msgs::msg::CameraInfo & message) const {
    if (message.header.frame_id != kPrivateFrame) return "frame_mismatch";
    if (message.width == 0 || message.height == 0) return "invalid_dimensions";
    size_t expected_d = 0;
    if (message.distortion_model == "plumb_bob") expected_d = 5;
    if (message.distortion_model == "rational_polynomial") expected_d = 8;
    if (message.distortion_model == "equidistant") expected_d = 4;
    const bool calibrated = expected_d != 0 && message.d.size() == expected_d &&
        finite_values(message.d) && finite_values(message.k) && finite_values(message.r) &&
        finite_values(message.p) && message.k[0] > 0 && message.k[4] > 0 &&
        message.k[8] == 1 && message.p[0] > 0 && message.p[5] > 0 &&
        message.p[10] == 1;
    return calibrated ? "" : "invalid_calibration";
  }

  template<typename Queue>
  void bound(Queue & queue, const char * stream) {
    while (queue.size() > kMaxQueue) {
      RCLCPP_ERROR(get_logger(), "%s matching queue overflow; dropping oldest candidate", stream);
      queue.erase(queue.begin());
      ++overflow_count_;
      errors_["synchronization"] = "queue_overflow";
    }
  }

  void receive_color(sensor_msgs::msg::Image::UniquePtr message) {
    const int64_t stamp = stamp_ns(message->header.stamp);
    const auto stamp_error = invalid_stamp_reason(stamp, last_color_stamp_);
    if (!stamp_error.empty()) { reject("color", stamp_error); return; }
    const auto content_error = invalid_color_reason(*message);
    if (!content_error.empty()) { reject("color", content_error); return; }
    last_color_stamp_ = stamp;
    color_arrival_ = steady_clock_.now().nanoseconds();
    colors_.emplace(stamp, std::move(message));
    bound(colors_, "color");
    match();
  }

  void receive_depth(sensor_msgs::msg::Image::UniquePtr message) {
    const int64_t stamp = stamp_ns(message->header.stamp);
    const auto stamp_error = invalid_stamp_reason(stamp, last_depth_stamp_);
    if (!stamp_error.empty()) { reject("depth", stamp_error); return; }
    const auto content_error = invalid_depth_reason(*message);
    if (!content_error.empty()) { reject("depth", content_error); return; }
    last_depth_stamp_ = stamp;
    depth_arrival_ = steady_clock_.now().nanoseconds();
    depths_.emplace(stamp, std::move(message));
    bound(depths_, "depth");
    match();
  }

  void receive_info(sensor_msgs::msg::CameraInfo::UniquePtr message) {
    const int64_t stamp = stamp_ns(message->header.stamp);
    const auto stamp_error = invalid_stamp_reason(stamp, last_info_stamp_);
    if (!stamp_error.empty()) { reject("calibration", stamp_error); return; }
    const auto content_error = invalid_info_reason(*message);
    if (!content_error.empty()) { reject("calibration", content_error); return; }
    last_info_stamp_ = stamp;
    info_arrival_ = steady_clock_.now().nanoseconds();
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
      if (depth != depths_.end()) observed_skew_ns_ = std::abs(depth->first - stamp);
      if (depth == depths_.end() || info == infos_.end()) {
        const bool depth_advanced = !depths_.empty() && depths_.rbegin()->first > stamp;
        const bool info_advanced = !infos_.empty() && infos_.rbegin()->first > stamp;
        const bool expired = get_clock()->now().nanoseconds() - stamp > kMaxAgeNs;
        if (blueboat_camera_adapter::reject_anchor(
              depth == depths_.end(), depth_advanced,
              info == infos_.end(), info_advanced, expired)) {
          RCLCPP_ERROR(get_logger(), "rejecting unmatched color anchor");
          ++unmatched_count_;
          errors_["synchronization"] = "unmatched_data";
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
        reject("registration", "invalid_dimensions");
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
        last_triple_stamp_ = stamp;
        last_triple_arrival_ = steady_clock_.now().nanoseconds();
        for (const auto & component : {"color", "depth", "calibration", "registration", "synchronization"}) {
          errors_.erase(component);
        }
      }
      colors_.erase(colors_.begin());
      depths_.erase(depth);
      infos_.erase(info);
    }
  }

  void receive_tf(const tf2_msgs::msg::TFMessage & message) {
    for (const auto & transform : message.transforms) {
      const auto & parent = transform.header.frame_id;
      const auto & child = transform.child_frame_id;
      if (child != "camera_0_link" && child != "camera_0_optical_frame") continue;
      const auto & t = transform.transform.translation;
      const auto & q = transform.transform.rotation;
      const bool valid = blueboat_camera_adapter::valid_camera_transform(
          parent, child, t.x, t.y, t.z, q.x, q.y, q.z, q.w);
      std::ostringstream signature;
      signature << parent << ':' << t.x << ':' << t.y << ':' << t.z << ':'
                << q.x << ':' << q.y << ':' << q.z << ':' << q.w;
      camera_transforms_[child].insert(signature.str());
      if (!valid || camera_transforms_[child].size() != 1) {
        errors_["frames"] = valid ? "duplicate_camera_transform" : "camera_transform_mismatch";
      }
    }
    frames_ready_ = camera_transforms_["camera_0_link"].size() == 1 &&
                    camera_transforms_["camera_0_optical_frame"].size() == 1 &&
                    errors_.count("frames") == 0;
  }

  template<typename Item>
  diagnostic_msgs::msg::KeyValue value(const std::string & key, const Item & item) const {
    std::ostringstream stream;
    stream << item;
    diagnostic_msgs::msg::KeyValue result;
    result.key = key;
    result.value = stream.str();
    return result;
  }

  diagnostic_msgs::msg::DiagnosticStatus component_status(
      const std::string & component, uint8_t default_level, const std::string & default_reason) const {
    diagnostic_msgs::msg::DiagnosticStatus output;
    output.name = "camera_adapter/camera_0/" + component;
    output.hardware_id = "simulation_adapter";
    auto error = errors_.find(component);
    output.level = error == errors_.end() ? default_level : diagnostic_msgs::msg::DiagnosticStatus::ERROR;
    output.message = error == errors_.end() ? default_reason : error->second;
    output.values = {
        value("contract_version", "1.0.0"), value("camera_id", "camera_0"),
        value("source_ready", output.level == diagnostic_msgs::msg::DiagnosticStatus::OK ? "true" : "false"),
        value("reason", output.message), value("rgb_depth_match_tolerance_ns", 0),
        value("max_acquisition_age_ns", kMaxAgeNs), value("max_arrival_silence_ns", 2000000000LL),
        value("color_header_stamp_ns", last_color_stamp_ ? std::to_string(last_color_stamp_) : "unobserved"),
        value("depth_header_stamp_ns", last_depth_stamp_ ? std::to_string(last_depth_stamp_) : "unobserved"),
        value("camera_info_header_stamp_ns", last_info_stamp_ ? std::to_string(last_info_stamp_) : "unobserved"),
        value("color_arrival_silence_ns", color_arrival_ ? std::to_string(steady_clock_.now().nanoseconds() - color_arrival_) : "unobserved"),
        value("depth_arrival_silence_ns", depth_arrival_ ? std::to_string(steady_clock_.now().nanoseconds() - depth_arrival_) : "unobserved"),
        value("camera_info_arrival_silence_ns", info_arrival_ ? std::to_string(steady_clock_.now().nanoseconds() - info_arrival_) : "unobserved"),
        value("rgb_depth_skew_ns", observed_skew_ns_ >= 0 ? std::to_string(observed_skew_ns_) : "unobserved"),
        value("rejected_count", rejected_count_), value("unmatched_count", unmatched_count_),
        value("overflow_count", overflow_count_),
    };
    return output;
  }

  void publish_diagnostics() {
    const int64_t steady_now = steady_clock_.now().nanoseconds();
    const int64_t ros_now = get_clock()->now().nanoseconds();
    auto stream_state = [&](int64_t stamp, int64_t arrival, const std::string & component) {
      auto error = errors_.find(component);
      if (error != errors_.end()) return std::make_pair(diagnostic_msgs::msg::DiagnosticStatus::ERROR, error->second);
      if (!stamp || !arrival) return std::make_pair(diagnostic_msgs::msg::DiagnosticStatus::STALE, std::string("unobserved"));
      if (ros_now < stamp) return std::make_pair(diagnostic_msgs::msg::DiagnosticStatus::ERROR, std::string("future_acquisition_stamp"));
      if (ros_now - stamp > kMaxAgeNs) return std::make_pair(diagnostic_msgs::msg::DiagnosticStatus::STALE, std::string("acquisition_timeout"));
      if (steady_now - arrival > 2000000000LL) return std::make_pair(diagnostic_msgs::msg::DiagnosticStatus::STALE, std::string("arrival_timeout"));
      return std::make_pair(diagnostic_msgs::msg::DiagnosticStatus::OK, std::string("ready"));
    };
    const auto color_state = stream_state(last_color_stamp_, color_arrival_, "color");
    const auto depth_state = stream_state(last_depth_stamp_, depth_arrival_, "depth");
    const auto info_state = stream_state(last_info_stamp_, info_arrival_, "calibration");
    const auto triple_state = stream_state(last_triple_stamp_, last_triple_arrival_, "synchronization");
    const auto frame_level = frames_ready_ ? diagnostic_msgs::msg::DiagnosticStatus::OK :
        (errors_.count("frames") ? diagnostic_msgs::msg::DiagnosticStatus::ERROR : diagnostic_msgs::msg::DiagnosticStatus::STALE);
    const std::string frame_reason = frames_ready_ ? "ready" :
        (errors_.count("frames") ? errors_.at("frames") : "transform_unobserved");
    diagnostic_msgs::msg::DiagnosticArray array;
    array.header.stamp = get_clock()->now();
    diagnostic_msgs::msg::DiagnosticStatus configuration;
    configuration.name = "camera_adapter/configuration";
    configuration.hardware_id = "simulation_adapter";
    configuration.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
    configuration.message = "valid";
    array.status.push_back(configuration);
    array.status.push_back(component_status("color", color_state.first, color_state.second));
    array.status.push_back(component_status("depth", depth_state.first, depth_state.second));
    array.status.push_back(component_status("calibration", info_state.first, info_state.second));
    array.status.push_back(component_status("registration", triple_state.first, triple_state.second));
    array.status.push_back(component_status("synchronization", triple_state.first, triple_state.second));
    array.status.push_back(component_status("frames", frame_level, frame_reason));
    uint8_t aggregate = diagnostic_msgs::msg::DiagnosticStatus::OK;
    std::string reason = "ready";
    for (const auto & item : array.status) {
      if (item.name == "camera_adapter/configuration") continue;
      if (item.level > aggregate) { aggregate = item.level; reason = item.message; }
    }
    const std::string aggregate_ready =
        aggregate == diagnostic_msgs::msg::DiagnosticStatus::OK ? "true" : "false";
    for (auto & item : array.status) {
      if (item.name == "camera_adapter/configuration") continue;
      for (auto & evidence : item.values) {
        if (evidence.key == "source_ready") evidence.value = aggregate_ready;
      }
    }
    array.status.push_back(component_status("source_readiness", aggregate, reason));
    diagnostics_pub_->publish(array);
  }

  std::map<int64_t, sensor_msgs::msg::Image::UniquePtr> colors_, depths_;
  std::map<int64_t, sensor_msgs::msg::CameraInfo::UniquePtr> infos_;
  int64_t last_color_stamp_{0}, last_depth_stamp_{0}, last_info_stamp_{0};
  int64_t color_arrival_{0}, depth_arrival_{0}, info_arrival_{0};
  int64_t last_triple_stamp_{0}, last_triple_arrival_{0}, observed_skew_ns_{-1};
  uint64_t rejected_count_{0}, unmatched_count_{0}, overflow_count_{0};
  std::map<std::string, std::string> errors_;
  std::map<std::string, std::set<std::string>> camera_transforms_;
  bool frames_ready_{false};
  rclcpp::Clock steady_clock_{RCL_STEADY_TIME};
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr color_pub_, depth_pub_;
  rclcpp::Publisher<sensor_msgs::msg::CameraInfo>::SharedPtr info_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diagnostics_pub_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr color_sub_, depth_sub_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr info_sub_;
  rclcpp::Subscription<tf2_msgs::msg::TFMessage>::SharedPtr tf_sub_;
  rclcpp::TimerBase::SharedPtr diagnostics_timer_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CameraBoundary>());
  rclcpp::shutdown();
  return 0;
}

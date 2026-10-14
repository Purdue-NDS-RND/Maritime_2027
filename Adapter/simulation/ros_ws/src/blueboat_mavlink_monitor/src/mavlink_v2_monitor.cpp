#include <arpa/inet.h>
#include <linux/if_ether.h>
#include <linux/if_packet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <memory>
#include <stdexcept>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include "blueboat_mavlink_monitor/packet.hpp"

class MavlinkV2Monitor final : public rclcpp::Node {
 public:
  MavlinkV2Monitor() : Node("mavlink_v2_monitor") {
    socket_ = ::socket(AF_PACKET, SOCK_RAW | SOCK_NONBLOCK, htons(ETH_P_IP));
    if (socket_ < 0) throw std::runtime_error("cannot open passive packet socket: " + std::string(std::strerror(errno)));
    // SITL normally reaches this container through its Docker network
    // interface, not loopback. An unbound AF_PACKET socket observes every
    // interface in this container namespace; packet.hpp still accepts only
    // IPv4 UDP traffic on the dedicated simulation port with MAVLink 2 magic.
    publisher_ = create_publisher<std_msgs::msg::Bool>(
        "/adapter/private/mavlink_v2_observed", rclcpp::QoS(1).transient_local().reliable());
    timer_ = create_wall_timer(std::chrono::milliseconds(20), [this]() { poll(); });
  }

  ~MavlinkV2Monitor() override { if (socket_ >= 0) ::close(socket_); }

 private:
  void poll() {
    std::array<uint8_t, 65536> packet{};
    for (;;) {
      const auto size = ::recv(socket_, packet.data(), packet.size(), 0);
      if (size < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) break;
      if (size < 0) throw std::runtime_error("passive packet receive failed");
      if (blueboat_mavlink_monitor::is_mavlink_v2_udp_14552(packet.data(), size)) observed_ = true;
    }
    std_msgs::msg::Bool message;
    message.data = observed_;
    publisher_->publish(message);
  }

  int socket_{-1};
  bool observed_{false};
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MavlinkV2Monitor>());
  rclcpp::shutdown();
  return 0;
}

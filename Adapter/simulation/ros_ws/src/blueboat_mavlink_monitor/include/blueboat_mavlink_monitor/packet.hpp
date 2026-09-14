#pragma once
#include <cstddef>
#include <cstdint>

namespace blueboat_mavlink_monitor {
inline bool is_mavlink_v2_udp_14552(const uint8_t * packet, size_t size) {
  if (size < 14 + 20 + 9) return false;
  constexpr size_t ip = 14;
  if ((packet[ip] >> 4) != 4 || packet[ip + 9] != 17) return false;
  const size_t ihl = static_cast<size_t>(packet[ip] & 0x0F) * 4;
  if (ihl < 20 || size < ip + ihl + 9) return false;
  const size_t udp = ip + ihl;
  const uint16_t source = static_cast<uint16_t>(packet[udp] << 8 | packet[udp + 1]);
  const uint16_t destination = static_cast<uint16_t>(packet[udp + 2] << 8 | packet[udp + 3]);
  return (source == 14552 || destination == 14552) && packet[udp + 8] == 0xFD;
}
}  // namespace blueboat_mavlink_monitor

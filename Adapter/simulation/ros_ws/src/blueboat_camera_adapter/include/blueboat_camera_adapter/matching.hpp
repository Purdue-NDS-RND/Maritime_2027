#pragma once

namespace blueboat_camera_adapter {
inline bool reject_anchor(
    bool depth_missing, bool depth_advanced,
    bool info_missing, bool info_advanced, bool expired) {
  return (depth_missing && depth_advanced) ||
         (info_missing && info_advanced) || expired;
}
}  // namespace blueboat_camera_adapter

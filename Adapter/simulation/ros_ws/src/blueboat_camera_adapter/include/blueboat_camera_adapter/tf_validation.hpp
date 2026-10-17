#pragma once
#include <cmath>
#include <string>

namespace blueboat_camera_adapter {
inline bool near(double actual, double expected) { return std::abs(actual - expected) <= 1e-6; }
inline bool valid_camera_transform(
    const std::string & parent, const std::string & child,
    double x, double y, double z, double qx, double qy, double qz, double qw,
    const std::string & camera = "camera_0", double mount_y = 0.0, double mount_yaw = 0.0) {
  if (child == camera + "_link") {
    return parent == "base_link" && near(x, 0.35) && near(y, mount_y) && near(z, 0.40) &&
           near(qx, 0.0) && near(qy, 0.0) && ((near(qz, std::sin(mount_yaw / 2)) && near(qw, std::cos(mount_yaw / 2))) ||
            (near(qz, -std::sin(mount_yaw / 2)) && near(qw, -std::cos(mount_yaw / 2))));
  }
  if (child == camera + "_optical_frame") {
    const bool quaternion =
        (near(qx, -0.5) && near(qy, 0.5) && near(qz, -0.5) && near(qw, 0.5)) ||
        (near(qx, 0.5) && near(qy, -0.5) && near(qz, 0.5) && near(qw, -0.5));
    return parent == camera + "_link" && near(x, 0.0) && near(y, 0.0) && near(z, 0.0) && quaternion;
  }
  return false;
}
}  // namespace blueboat_camera_adapter

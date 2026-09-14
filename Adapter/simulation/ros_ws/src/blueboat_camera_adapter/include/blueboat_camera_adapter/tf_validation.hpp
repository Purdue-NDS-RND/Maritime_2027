#pragma once
#include <cmath>
#include <string>

namespace blueboat_camera_adapter {
inline bool near(double actual, double expected) { return std::abs(actual - expected) <= 1e-6; }
inline bool valid_camera_transform(
    const std::string & parent, const std::string & child,
    double x, double y, double z, double qx, double qy, double qz, double qw) {
  if (child == "camera_0_link") {
    return parent == "base_link" && near(x, 0.35) && near(y, 0.0) && near(z, 0.40) &&
           near(qx, 0.0) && near(qy, 0.0) && near(qz, 0.0) && near(std::abs(qw), 1.0);
  }
  if (child == "camera_0_optical_frame") {
    const bool quaternion =
        (near(qx, -0.5) && near(qy, 0.5) && near(qz, -0.5) && near(qw, 0.5)) ||
        (near(qx, 0.5) && near(qy, -0.5) && near(qz, 0.5) && near(qw, -0.5));
    return parent == "camera_0_link" && near(x, 0.0) && near(y, 0.0) && near(z, 0.0) && quaternion;
  }
  return false;
}
}  // namespace blueboat_camera_adapter

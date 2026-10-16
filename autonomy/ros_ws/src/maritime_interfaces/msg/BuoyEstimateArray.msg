# Stamp of the source RGB observation; frame of the estimated XY points.
std_msgs/Header header
string method
# not_implemented, waiting_for_inputs, ok, or error. Empty estimates alone
# do not distinguish an unfinished method from a successful empty observation.
string status
string detail
bool inputs_ready
# Original source headers, retained without attempting clock synchronization.
builtin_interfaces/Time vessel_pose_stamp
builtin_interfaces/Time depth_stamp
maritime_interfaces/BuoyEstimate[] estimates

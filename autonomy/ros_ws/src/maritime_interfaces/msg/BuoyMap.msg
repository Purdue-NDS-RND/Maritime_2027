std_msgs/Header header
string session_id
bool paused
string detail
# Metric records only. Tentative is distinct from navigation-usable confirmed.
maritime_interfaces/BuoyTrack[] tracks
uint32 unresolved_count
# Active tracks without metric range. Retired IDs are absent from this snapshot.
string[] unresolved_world_ids

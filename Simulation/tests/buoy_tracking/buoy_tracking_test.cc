// Exercise the real Gazebo plugin and static-model physics pose updates.
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <gz/sim/Model.hh>
#include <gz/sim/SdfEntityCreator.hh>
#include <gz/sim/TestFixture.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <sdf/Root.hh>
#include <sdf/Model.hh>

void Require(bool condition, const std::string &message)
{
  if (!condition) throw std::runtime_error(message);
}

int main(int argc, char **argv)
{
  Require(argc == 2, "pass a temporary world filename");
  std::ofstream worldFile(argv[1]);
  worldFile << "<sdf version='1.9'><world name='tracking_test'>"
      "<physics name='physics' type='ignored'><max_step_size>0.001</max_step_size>"
      "<real_time_factor>0</real_time_factor></physics>"
      "<plugin filename='gz-sim-physics-system' name='gz::sim::systems::Physics'/>";
  for (int id = 0; id < 4; ++id)
    worldFile << "<include><uri>model://aruco_buoy_id" << id
        << "</uri><name>category_" << id << "</name><pose>" << id * 2
        << " 0 0 0 0 0.4</pose></include>";
  worldFile << "</world></sdf>";
  worldFile.close();

  gz::sim::TestFixture fixture(argv[1]);
  gz::sim::Entity world = gz::sim::kNullEntity;
  gz::sim::EventManager *events = nullptr;
  int step = 0, checks = 0;
  fixture.OnConfigure([&](auto entity, auto, auto &, auto &eventManager)
  {
    world = entity;
    events = &eventManager;
  });
  fixture.OnPreUpdate([&](const auto &, auto &ecm)
  {
    gz::sim::SdfEntityCreator creator(ecm, *events);
    // Initially there is no boat. Insert one after the server has started.
    if (step == 10)
    {
      sdf::Root root;
      Require(root.LoadSdfString("<sdf version='1.9'><model name='blueboat'>"
          "<static>true</static><link name='base_link'/></model></sdf>").empty(),
          "could not parse late boat");
      creator.SetParent(creator.CreateEntities(root.Model()), world);
    }
    // A second red buoy is inserted during the orbit, sharing category ID 1.
    if (step == 200)
    {
      sdf::Root root;
      Require(root.Load("/opt/boat_sim/models/aruco_buoy_id1/model.sdf").empty(),
          "could not load late buoy");
      auto model = *root.Model();
      model.SetName("late_red");
      model.SetRawPose(gz::math::Pose3d(3, 3, 0, 0, 0, 0));
      creator.SetParent(creator.CreateEntities(&model), world);
    }
    auto boat = ecm.EntityByComponents(gz::sim::components::Model(),
        gz::sim::components::Name("blueboat"));
    if (boat != gz::sim::kNullEntity)
    {
      // Move around a complete circle, then hold at coincident XY positions.
      double angle = 2 * GZ_PI * std::min(step - 10, 720) / 720.0;
      auto pose = step >= 740 ? gz::math::Pose3d::Zero :
          gz::math::Pose3d(3 + 9 * std::cos(angle), 9 * std::sin(angle),
              0, 0, 0, angle + GZ_PI);
      gz::sim::Model(boat).SetWorldPoseCmd(ecm, pose);
    }
    ++step;
  });
  fixture.OnPostUpdate([&](const auto &, const auto &ecm)
  {
    auto boat = ecm.EntityByComponents(gz::sim::components::Model(),
        gz::sim::components::Name("blueboat"));
    for (int id = 0; id < 5; ++id)
    {
      if (id == 4 && step < 205) continue;
      auto name = id == 4 ? "late_red" : "category_" + std::to_string(id);
      auto entity = ecm.EntityByComponents(gz::sim::components::Model(),
          gz::sim::components::Name(name));
      Require(entity != gz::sim::kNullEntity, "missing buoy " + name);
      auto pose = gz::sim::worldPose(entity, ecm);
      auto expectedPosition = id == 4 ? gz::math::Vector3d(3, 3, 0) :
          gz::math::Vector3d(id * 2, 0, 0);
      Require(pose.Pos().Distance(expectedPosition) < 1e-6, "buoy moved " + name);
      Require(std::abs(pose.Rot().Roll()) < 1e-6 &&
          std::abs(pose.Rot().Pitch()) < 1e-6, "buoy tilted " + name);
      if (step < 10)
        Require(std::abs(pose.Rot().Yaw() - 0.4) < 1e-6, "changed without boat");
      if (boat == gz::sim::kNullEntity || step < 15 ||
          (step >= 740 && step < 745)) continue;
      auto delta = gz::sim::worldPose(boat, ecm).Pos() - pose.Pos();
      Require(std::isfinite(pose.Rot().Yaw()), "nonfinite yaw");
      if (delta.Length() < 1e-6) continue;
      auto face = pose.Rot().RotateVector(gz::math::Vector3d::UnitX);
      // One physics-step latency while the target is moving is allowed.
      Require(face.Dot(delta.Normalized()) > 0.9998, "buoy faces away " + name);
      ++checks;
    }
  }).Finalize();
  Require(fixture.Server()->Run(true, 760, false), "server failed");
  Require(checks > 3000, "too few tracking observations");
  std::cout << "Buoy tracking PASS: " << checks << " facing checks; full circle, "
      "all colors, late boat/buoy spawn, fixed centers, coincident target.\n";
}

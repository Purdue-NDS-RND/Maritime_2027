// Simulation-only presentation aid: keep the +X marker face toward the boat.
#include <cmath>
#include <memory>
#include <string>

#include <gz/plugin/Register.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/ParentEntity.hh>
#include <sdf/Element.hh>

namespace maritime
{
class BuoyFaceBoat final : public gz::sim::System,
                          public gz::sim::ISystemConfigure,
                          public gz::sim::ISystemPreUpdate
{
  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &,
      gz::sim::EventManager &) override
  {
    this->buoy = gz::sim::Model(_entity);
    if (_sdf->HasElement("boat_name"))
      this->boatName = _sdf->Get<std::string>("boat_name");
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &_ecm) override
  {
    if (_info.paused || !this->buoy.Valid(_ecm))
      return;
    const auto parent = _ecm.Component<gz::sim::components::ParentEntity>(
        this->buoy.Entity());
    if (!parent)
      return;
    this->world = parent->Data();
    // Resolve again if the target is removed; also handles late boat spawning.
    if (!_ecm.HasEntity(this->boat))
      this->boat = _ecm.EntityByComponents(gz::sim::components::Model(),
          gz::sim::components::Name(this->boatName),
          gz::sim::components::ParentEntity(this->world));
    if (this->boat == gz::sim::kNullEntity)
      return;
    auto pose = gz::sim::worldPose(this->buoy.Entity(), _ecm);
    const auto target = gz::sim::worldPose(this->boat, _ecm).Pos();
    const auto delta = target - pose.Pos();
    // The bearing is undefined at coincident XY positions. Keep the last yaw.
    if (std::hypot(delta.X(), delta.Y()) < 1e-6)
      return;
    pose.Rot() = gz::math::Quaterniond(0, 0,
        std::atan2(delta.Y(), delta.X()));
    this->buoy.SetWorldPoseCmd(_ecm, pose);
  }

  private: gz::sim::Model buoy{gz::sim::kNullEntity};
  private: gz::sim::Entity boat{gz::sim::kNullEntity};
  private: gz::sim::Entity world{gz::sim::kNullEntity};
  private: std::string boatName{"blueboat"};
};
}

GZ_ADD_PLUGIN(maritime::BuoyFaceBoat, gz::sim::System,
    maritime::BuoyFaceBoat::ISystemConfigure,
    maritime::BuoyFaceBoat::ISystemPreUpdate)
GZ_ADD_PLUGIN_ALIAS(maritime::BuoyFaceBoat, "maritime::BuoyFaceBoat")

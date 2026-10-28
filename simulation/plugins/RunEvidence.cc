// Simulation-only disk recorder. No transport publishers or control access.
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <memory>
#include <string>
#include <gz/plugin/Register.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/sim/components/Link.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/ParentEntity.hh>
#include <sdf/Element.hh>

namespace maritime {
class RunEvidence final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemPostUpdate {
 public:
  void Configure(const gz::sim::Entity &, const std::shared_ptr<const sdf::Element> &sdf,
                 gz::sim::EntityComponentManager &, gz::sim::EventManager &) override {
    output.open(sdf->Get<std::string>("path"), std::ios::out | std::ios::trunc);
    output << std::setprecision(17);
    if (!output) throw std::runtime_error("cannot open independent evidence file");
  }
  void PreUpdate(const gz::sim::UpdateInfo &, gz::sim::EntityComponentManager &ecm) override {
    ecm.Each<gz::sim::components::Collision>([&](const auto entity, const auto *) {
      if (!ecm.Component<gz::sim::components::ContactSensorData>(entity))
        ecm.CreateComponent(entity, gz::sim::components::ContactSensorData());
      return true;
    });
  }
  void PostUpdate(const gz::sim::UpdateInfo &info,
                  const gz::sim::EntityComponentManager &ecm) override {
    if (info.paused) return;
    output << "{\"iteration\":" << info.iterations << ",\"time_s\":"
           << std::chrono::duration<double>(info.simTime).count()
           << ",\"dt_s\":" << std::chrono::duration<double>(info.dt).count()
           << ",\"poses\":[";
    bool first = true;
    ecm.Each<gz::sim::components::Name, gz::sim::components::ParentEntity>(
      [&](const auto entity, const auto *name, const auto *parent) {
        bool record = false;
        std::string key = name->Data();
        if (ecm.Component<gz::sim::components::Model>(entity))
          record = key != "water_surface";
        if (ecm.Component<gz::sim::components::Link>(entity)) {
          const auto *pname = ecm.Component<gz::sim::components::Name>(parent->Data());
          if (pname && pname->Data() == "blueboat") {
            record = true; key = "blueboat/" + key;
          }
        }
        if (!record) return true;
        const auto pose = gz::sim::worldPose(entity, ecm);
        const auto rpy = pose.Rot().Euler();
        if (!first) output << ',';
        first = false;
        output << "{\"name\":\"" << key << "\",\"pose\":[" << pose.X() << ','
               << pose.Y() << ',' << pose.Z() << ',' << rpy.X() << ',' << rpy.Y()
               << ',' << rpy.Z() << "]}";
        return true;
      });
    output << "],\"contacts\":[";
    first = true;
    ecm.Each<gz::sim::components::ContactSensorData>([&](const auto, const auto *data) {
      for (const auto &contact : data->Data().contact()) {
        if (!first) output << ',';
        first = false;
        output << "{\"collision1_id\":" << contact.collision1().id()
               << ",\"collision2_id\":" << contact.collision2().id()
               << ",\"collision1_name\":\""
               << gz::sim::scopedName(contact.collision1().id(), ecm, "::", false)
               << "\",\"collision2_name\":\""
               << gz::sim::scopedName(contact.collision2().id(), ecm, "::", false)
               << "\"}";
      }
      return true;
    });
    output << "]}\n";
    if (info.iterations % 1000 == 0) output.flush();
  }
 private:
  std::ofstream output;
};
}
GZ_ADD_PLUGIN(maritime::RunEvidence, gz::sim::System,
    maritime::RunEvidence::ISystemConfigure, maritime::RunEvidence::ISystemPreUpdate,
    maritime::RunEvidence::ISystemPostUpdate)
GZ_ADD_PLUGIN_ALIAS(maritime::RunEvidence, "maritime::RunEvidence")

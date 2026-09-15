"""Static checks for Task 08's simulation-only autonomy boundary."""

from pathlib import Path
import sys
import unittest


AUTONOMY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = AUTONOMY_ROOT / "ros_ws" / "src" / "maritime_bringup"
sys.path.insert(0, str(PACKAGE_ROOT))

from maritime_bringup.bootstrap_policy import validate_environment


class Task08BoundaryTests(unittest.TestCase):
    def test_bootstrap_requires_explicit_simulation_opt_in(self):
        self.assertIsNone(validate_environment("simulation", "1"))
        self.assertEqual(
            validate_environment(None, "1"),
            "adapter_environment_not_simulation",
        )
        self.assertEqual(
            validate_environment("hardware", "1"),
            "adapter_environment_not_simulation",
        )
        self.assertEqual(
            validate_environment("simulation", None),
            "placeholder_opt_in_missing",
        )

    def test_autonomy_image_excludes_adapter_owned_runtime(self):
        dockerfile = (AUTONOMY_ROOT / "container" / "Dockerfile").read_text()
        for forbidden in ("mavros", "geographiclib", "FCU_URL"):
            self.assertNotIn(forbidden, dockerfile)

    def test_autonomy_package_excludes_environment_dependencies(self):
        package_xml = (PACKAGE_ROOT / "package.xml").read_text()
        for forbidden in ("mavros", "gazebo", "ros_gz", "zed", "geographiclib"):
            self.assertNotIn(forbidden, package_xml.lower())

    def test_only_the_named_placeholder_entrypoints_remain(self):
        setup_py = (PACKAGE_ROOT / "setup.py").read_text()
        self.assertIn("preimplementation_placeholder", setup_py)
        self.assertIn("placeholder_healthcheck", setup_py)
        self.assertNotIn("healthcheck = maritime_bringup.healthcheck", setup_py)
        self.assertFalse((PACKAGE_ROOT / "launch" / "vehicle.launch.py").exists())


if __name__ == "__main__":
    unittest.main()

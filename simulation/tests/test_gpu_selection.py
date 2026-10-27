"""Exercise GPU selection and runtime failure without creating containers."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GpuSelectionTests(unittest.TestCase):
    def select(self, mode, software='0', available=True):
        environment = dict(os.environ, SIM_GPU=mode, SOFTWARE_RENDERING=software,
                           SIM_IMAGE='test-image', PROBE_OK='1' if available else '0')
        script = '''
source scripts/select-gpu.sh
compose_files=(-f container/compose.yaml)
timeout() { shift; "$@"; }
docker() { echo PROBE_CALLED >&2; [[ $PROBE_OK == 1 ]]; }
select_simulation_gpu
result=$?
printf 'resolved=%s files=%s\n' "$SIM_GPU_RESOLVED" "${compose_files[*]}"
exit "$result"
'''
        return subprocess.run(['bash', '-c', script], cwd=ROOT, env=environment,
                              capture_output=True, text=True, timeout=5)

    def test_discrete_graphics_requires_a_successful_runtime_probe(self):
        result = self.select('nvidia')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('resolved=nvidia', result.stdout)
        self.assertIn('container/compose.nvidia.yaml', result.stdout)
        result = self.select('nvidia', available=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('NVIDIA container graphics is unavailable', result.stderr)
        self.assertNotIn('container/compose.nvidia.yaml', result.stdout)

    def test_mesa_and_software_do_not_probe_nvidia(self):
        for mode, software, resolved in [('mesa', '0', 'mesa'), ('auto', '1', 'software')]:
            with self.subTest(mode=mode, software=software):
                result = self.select(mode, software)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('resolved='+resolved, result.stdout)
                self.assertNotIn('PROBE_CALLED', result.stderr)

    def test_conflicting_or_invalid_configuration_is_rejected(self):
        for mode, software in [('nvidia', '1'), ('typo', '0')]:
            self.assertNotEqual(self.select(mode, software).returncode, 0)

    @unittest.skipUnless(Path('/dev/nvidiactl').exists(), 'automatic NVIDIA path requires NVIDIA host')
    def test_auto_reports_broken_runtime_and_falls_back(self):
        result = self.select('auto', available=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn('resolved=mesa', result.stdout)
        self.assertIn('container runtime failed', result.stderr)
        self.assertNotIn('container/compose.nvidia.yaml', result.stdout)


if __name__ == '__main__':
    unittest.main()

"""Isolated real-physics recorder regression, with no SITL or vehicle commands."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(shutil.which('gz'), 'requires simulator image')
class ContactRecordingTests(unittest.TestCase):
    def test_named_contacts_and_contiguous_physics_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);recording=root/'truth.jsonl'
            world=f'''<sdf version="1.9"><world name="contact_probe">
              <physics name="step" type="ignored"><max_step_size>0.001</max_step_size></physics>
              <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
              <plugin filename="libRunEvidence.so" name="maritime::RunEvidence"><path>{recording}</path></plugin>
              <model name="slalom_probe"><static>true</static><link name="base_link"><collision name="collision"><geometry><box><size>1 1 1</size></box></geometry></collision></link></model>
              <model name="blueboat"><pose>0 0 0.25 0 0 0</pose><link name="base_link"><inertial><mass>1</mass><inertia><ixx>1</ixx><iyy>1</iyy><izz>1</izz></inertia></inertial><collision name="collision"><geometry><box><size>1 1 1</size></box></geometry></collision></link></model>
              </world></sdf>'''
            (root/'probe.sdf').write_text(world)
            env={**os.environ,'GZ_PARTITION':'maritime_evidence_probe_'+str(os.getpid())}
            with(root/'server.log').open('w')as log:
                process=subprocess.Popen(['gz','sim','-s','-r',str(root/'probe.sdf')],env=env,
                                         stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline:
                        if process.poll() is not None:break
                        if recording.exists() and recording.stat().st_size>10000:break
                        time.sleep(.1)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid,signal.SIGKILL);process.wait()
            self.assertTrue(recording.exists(),(root/'server.log').read_text())
            rows=[json.loads(line)for line in recording.read_text().splitlines()]
            self.assertGreater(len(rows),10)
            contacts=[c for row in rows for c in row['contacts']]
            self.assertTrue(contacts,(root/'server.log').read_text())
            self.assertTrue(any('blueboat' in c['collision1_name']+c['collision2_name'] and
                                'slalom_probe' in c['collision1_name']+c['collision2_name']for c in contacts))
            self.assertTrue(all(b['iteration']==a['iteration']+1 for a,b in zip(rows,rows[1:])))


if __name__=='__main__':unittest.main()

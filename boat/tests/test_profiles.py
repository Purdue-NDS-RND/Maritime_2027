import json
from pathlib import Path
import tempfile
import unittest
from boat_app.executor import MissionError
from boat_app.profiles import verify_profile


class ProfileTests(unittest.TestCase):
    def test_firmware_geometry_and_live_parameters_must_match(self):
        class Controller:
            firmware_version=None
            firmware_hash=None
            def command(self,*args):self.firmware_version=67567871;self.firmware_hash='1511f271'
            def parameter(self,name):return 3 if name=='WP_RADIUS' else 0
            def emit(self,event):pass
        with tempfile.TemporaryDirectory() as directory:
            profile={'id':'test','status':'calibrated','geometry_sha256':'geometry',
                     'firmware':{'flight_sw_version':67567871,'git_hash_short':'1511f271'},
                     'parameters':{'WP_RADIUS':3,'WP_PIVOT_ANGLE':0,'WP_PIVOT_RATE':0,'WP_ACCEL':0,'WP_JERK':0}}
            path=Path(directory,'test.json');path.write_text(json.dumps(profile))
            verify_profile(Controller(),'test',directory,'geometry')
            with self.assertRaisesRegex(MissionError,'geometry'):
                verify_profile(Controller(),'test',directory,'wrong')
            profile['parameters']['WP_RADIUS']=.2;path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError,'WP_RADIUS'):
                verify_profile(Controller(),'test',directory,'geometry')
            profile['firmware']['git_hash_short']='different';path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError,'source hash'):
                verify_profile(Controller(),'test',directory,'geometry')

import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from boat_app.executor import MissionError
from boat_app.profiles import verify_profile


def next_position(controller, predicate, timeout=2):
    controller.position_ms = getattr(controller, 'position_ms', 0) + getattr(controller, 'position_step_ms', 250)
    return SimpleNamespace(time_boot_ms=controller.position_ms, get_type=lambda:'GLOBAL_POSITION_INT')


class ProfileTests(unittest.TestCase):
    def test_firmware_geometry_and_live_parameters_must_match(self):
        class Controller:
            wait=next_position
            firmware_version=None
            firmware_hash=None
            def command(self,*args):self.firmware_version=67567871;self.firmware_hash='1511f271'
            def parameter(self,name):return {'WP_RADIUS':3,'ATC_STR_RAT_FF':.2,'ATC_SPEED_P':.1,'ATC_SPEED_I':.2}.get(name,0)
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

    def test_explicit_and_legacy_steering_gain_are_verified(self):
        class Controller:
            wait=next_position
            firmware_version = None
            firmware_hash = None
            def command(self, *args):
                self.firmware_version = 67567871
                self.firmware_hash = '1511f271'
            def parameter(self, name):
                return {'WP_RADIUS':3,'ATC_STR_RAT_FF':.8,'ATC_SPEED_P':.1,'ATC_SPEED_I':.2}.get(name,0)
            def emit(self, event):
                pass
        with tempfile.TemporaryDirectory() as directory:
            profile = {'id':'test','status':'calibrated','geometry_sha256':'geometry',
                       'firmware':{'flight_sw_version':67567871,'git_hash_short':'1511f271'},
                       'parameters':{'WP_RADIUS':3,'WP_PIVOT_ANGLE':0,'WP_PIVOT_RATE':0,'WP_ACCEL':0,'WP_JERK':0}}
            path = Path(directory, 'test.json')
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError, 'ATC_STR_RAT_FF'):
                verify_profile(Controller(), 'test', directory, 'geometry')
            profile['parameters']['ATC_STR_RAT_FF'] = .8
            path.write_text(json.dumps(profile))
            verify_profile(Controller(), 'test', directory, 'geometry')
            profile['parameters']['ATC_STR_RAT_FF'] = .5
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError, 'ATC_STR_RAT_FF'):
                verify_profile(Controller(), 'test', directory, 'geometry')
            del profile['parameters']['WP_JERK']
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError, 'five waypoint'):
                verify_profile(Controller(), 'test', directory, 'geometry')

    def test_speed_gains_and_finite_values_are_verified(self):
        current = {'WP_RADIUS':3,'ATC_STR_RAT_FF':.8,'ATC_SPEED_P':.5,'ATC_SPEED_I':.1}
        class Controller:
            wait=next_position
            firmware_version = None
            firmware_hash = None
            def command(self, *args):
                self.firmware_version = 67567871
                self.firmware_hash = '1511f271'
            def parameter(self, name):
                return current.get(name, 0)
            def emit(self, event):
                pass
        with tempfile.TemporaryDirectory() as directory:
            profile = {'id':'test','status':'calibrated','geometry_sha256':'geometry',
                       'firmware':{'flight_sw_version':67567871,'git_hash_short':'1511f271'},
                       'parameters':{'WP_RADIUS':3,'WP_PIVOT_ANGLE':0,'WP_PIVOT_RATE':0,
                                     'WP_ACCEL':0,'WP_JERK':0,'ATC_STR_RAT_FF':.8}}
            path = Path(directory, 'test.json')
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError, 'ATC_SPEED_P'):
                verify_profile(Controller(), 'test', directory, 'geometry')
            profile['parameters'].update(ATC_SPEED_P=.5, ATC_SPEED_I=.1)
            path.write_text(json.dumps(profile))
            verify_profile(Controller(), 'test', directory, 'geometry')
            profile['parameters']['ATC_SPEED_P'] = float('nan')
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError, 'finite'):
                verify_profile(Controller(), 'test', directory, 'geometry')
            profile['parameters']['ATC_SPEED_P'] = .5
            path.write_text(json.dumps(profile))
            current['ATC_SPEED_P'] = float('nan')
            with self.assertRaisesRegex(MissionError, 'ATC_SPEED_P'):
                verify_profile(Controller(), 'test', directory, 'geometry')

    def test_profile_position_rate_requires_supported_acknowledged_request(self):
        class Controller:
            wait=next_position
            firmware_version = None
            firmware_hash = None
            def __init__(self, ignore_request=False):
                self.commands = []
                self.ignore_request = ignore_request
            def command(self, *args):
                self.commands.append(args)
                if args[0] == 511 and not self.ignore_request:
                    self.position_step_ms = args[2]/1000
                self.firmware_version = 67567871
                self.firmware_hash = '1511f271'
            def parameter(self, name):
                return {'WP_RADIUS':3,'ATC_STR_RAT_FF':.2,'ATC_SPEED_P':.1,'ATC_SPEED_I':.2}.get(name,0)
            def emit(self, event):
                pass
        with tempfile.TemporaryDirectory() as directory:
            profile = {'id':'test','status':'calibrated','geometry_sha256':'geometry',
                       'position_rate_hz':20,
                       'firmware':{'flight_sw_version':67567871,'git_hash_short':'1511f271'},
                       'parameters':{'WP_RADIUS':3,'WP_PIVOT_ANGLE':0,'WP_PIVOT_RATE':0,'WP_ACCEL':0,'WP_JERK':0}}
            path = Path(directory, 'test.json')
            path.write_text(json.dumps(profile))
            controller = Controller()
            verify_profile(controller, 'test', directory, 'geometry')
            self.assertIn((511, 33, 50000), controller.commands)
            with self.assertRaisesRegex(MissionError, 'observed position'):
                verify_profile(Controller(ignore_request=True), 'test', directory, 'geometry')
            profile['position_rate_hz'] = 5
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(MissionError, 'telemetry rate'):
                verify_profile(Controller(), 'test', directory, 'geometry')

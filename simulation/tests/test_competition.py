"""Competition geometry, immutable exports and clearance, with legacy regression."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'simulation/scripts'))
from export_map import export
from shared.geometry import to_gps, to_local
from shared.object_map import validate_map
from shared.clearance import validate_route


class CompetitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.render()
        self.manifest = json.loads((self.root/'manifest.json').read_text())
        boat = self.root/'models/blueboat'
        boat.mkdir(parents=True)
        (boat/'model.sdf').write_text('''<sdf><model><link name="imu_link"/><plugin name="ArduPilotPlugin">
            <gazeboXYZToNED degrees="true">0 0 0 180 0 90</gazeboXYZToNED>
            <modelXYZToAirplaneXForwardZDown degrees="true">0 0 0 180 0 0</modelXYZToAirplaneXForwardZDown>
            </plugin></model></sdf>''')
        self.seal()
        self.data = export(self.root,self.identity['scene_id'],'test')
        self.data['alignment'] = {'outcome':'passed'}

    def render(self):
        subprocess.run([sys.executable,str(ROOT/'simulation/scripts/render_scenario.py'),
                        '--scenario',str(ROOT/'simulation/scenarios/competition.json'),
                        '--base-world',str(ROOT/'simulation/worlds/blueboat_rgbd_base.sdf'),
                        '--output-world',str(self.root/'world.sdf'),'--manifest',str(self.root/'manifest.json'),
                        '--cameras','off'],check=True,capture_output=True)

    def seal(self):
        self.identity = {'run_id':'test','geographic_reference':{'latitude':51.566151,'longitude':-4.034345},
                         'files':{str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in self.root.rglob('*') if p.is_file() and p.name != 'scene.json'}}
        self.identity['scene_id'] = hashlib.sha256(json.dumps(self.identity,sort_keys=True).encode()).hexdigest()
        (self.root/'scene.json').write_text(json.dumps(self.identity))

    def test_distances_colours_spawn_and_station_completeness(self):
        objects = {o['name']:o for o in self.manifest['buoys']+self.manifest['props']}
        for obj in objects.values():
            for i,key in enumerate(('x','y')):
                self.assertAlmostEqual(obj['model_pose'][key],obj['reference_ft'][i]*.3048+(3 if i==0 else 0))
        self.assertAlmostEqual(abs(objects['dodge_gate_a_red']['model_pose']['y']-objects['dodge_gate_a_green']['model_pose']['y']),4)
        self.assertEqual([objects[f'dodge_turn_{i}']['category'] for i in range(1,5)],['red','green','red','green'])
        self.assertEqual({objects['identify_'+c]['category'] for c in ['blue','orange','purple','yellow']},{'blue','orange','purple','yellow'})
        self.assertEqual({s['id'] for s in self.data['stations']},{'start','dodge','evade','identify','deploy','launch','recover','receive','return','deployment_radius'})
        self.assertEqual(self.data['start_pose']['heading_deg'],270)
        self.assertEqual(self.manifest['boat_pose']['yaw_rad'],math.pi)
        self.assertEqual(len(self.data['buoys']),23)
        self.assertEqual(len(self.data['obstacles']),6)
        from competition_scene import COLOURS
        tree = ET.parse(self.root/'world.sdf')
        for name,obj in objects.items():
            self.assertEqual(tree.findtext(f"./world/model[@name='{name}']/link/visual/material/diffuse"),COLOURS[obj['category']])

    def test_deterministic_render_and_export_identity(self):
        world = (self.root/'world.sdf').read_bytes()
        self.render()
        self.assertEqual(world,(self.root/'world.sdf').read_bytes())
        validate_map(self.data)
        self.assertEqual({o['id'] for o in self.data['buoys']+self.data['obstacles']},
                         {o['name'] for o in self.manifest['buoys']+self.manifest['props']})
        tree = ET.parse(self.root/'world.sdf')
        tree.find("./world/model[@name='start_dock']/link/collision/geometry/box/size").text='5 6 0.5'
        tree.write(self.root/'world.sdf')
        with self.assertRaisesRegex(ValueError,'changed'):
            export(self.root,self.identity['scene_id'],'test')

    def draft(self,a,b):
        ref = self.data['geographic_reference']
        return {'task':'custom','start':to_gps(*a,ref),'waypoints':[to_gps(*b,ref)],'finish':to_gps(*b,ref),
                'speed_m_s':.5,'clearance_m':.5,'finish_radius_m':.5,'passages':[]}

    def test_every_physical_object_rejects_crossing_and_finish(self):
        ref = self.data['geographic_reference']
        for obj in self.data['buoys']+self.data['obstacles']:
            with self.subTest(obj=obj['id']):
                x,y = to_local(obj['centre'],ref)
                result = validate_route(self.data,self.draft((x-5,y),(x+5,y)))
                self.assertTrue(any('leg 0 ' in e['reason'] and obj['id'] in e['reason'] for e in result['errors']))
                result = validate_route(self.data,self.draft((x-5,y),(x,y)))
                self.assertTrue(any('finish area' in e['reason'] and obj['id'] in e['reason'] for e in result['errors']))
        self.assertTrue(validate_route(self.data,self.draft((0,0),(-5,0)))['valid'])
        # Overlay is nonblocking away from its physical Zebra buoy.
        x,y = to_local(next(o['centre'] for o in self.data['buoys'] if o['id']=='deploy_zebra'),ref)
        self.assertTrue(validate_route(self.data,self.draft((x-3,y+1.5),(x+3,y+1.5)))['valid'])

    def test_invalid_geometry_and_identity_rejected(self):
        for kind in ('negative','nan','duplicate','bowtie','collinear','heading'):
            data = deepcopy(self.data)
            if kind=='negative':data['buoys'][0]['radius_m']=-1
            if kind=='nan':data['obstacles'][0]['footprint'][0]['latitude']=float('nan')
            if kind=='duplicate':data['obstacles'][0]['id']=data['buoys'][0]['id']
            if kind=='bowtie':
                p=data['obstacles'][0]['footprint'];p[1],p[2]=p[2],p[1]
            if kind=='collinear':data['obstacles'][0]['footprint']=[data['obstacles'][0]['centre']]*3
            if kind=='heading':data['start_pose']['heading_deg']=float('inf')
            with self.subTest(kind=kind),self.assertRaises(ValueError):validate_map(data)

    def test_export_rejects_unlisted_model_and_pose_mismatch(self):
        tree = ET.parse(self.root/'world.sdf')
        tree.find("./world/model[@name='start_dock']/pose").text='0 0 0 0 0 0'
        tree.write(self.root/'world.sdf');self.seal()
        with self.assertRaisesRegex(ValueError,'pose mismatch'):export(self.root,self.identity['scene_id'],'test')
        self.render()
        tree = ET.parse(self.root/'world.sdf')
        ET.SubElement(tree.find('world'),'model',name='unlisted')
        tree.write(self.root/'world.sdf');self.seal()
        with self.assertRaisesRegex(ValueError,'missing competition models'):export(self.root,self.identity['scene_id'],'test')


if __name__ == '__main__':
    unittest.main()

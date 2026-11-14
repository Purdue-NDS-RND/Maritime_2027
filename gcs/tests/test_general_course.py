"""General geometry, local progress, attempt authorization and migration."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from gcs.app.attempts import capture_start, check_remaining_snapshot
from gcs.app.planner import generate
from gcs.app.workspace import Workspace
from shared.course import Course
from shared.geometry import to_gps, to_local
from shared.task_geometry import resolve_geometry, remaining_suggestion


class GeneralCourseTests(unittest.TestCase):
    def fixture(self, angle=0, offset=(0,0), channel=False):
        ref={'latitude':51.5,'longitude':-4}
        def gps(x,y):
            return to_gps(offset[0]+x*math.cos(angle)-y*math.sin(angle),offset[1]+x*math.sin(angle)+y*math.cos(angle),ref)
        objects=[]
        coords=([('l0',0,6),('l1',12,6),('l2',24,12),('r0',0,-6),('r1',14,-6),('r2',28,0)] if channel else
                [('a',0,-5),('b',0,5),('t',10,2),('c',23,0),('d',25,10)])
        for name,x,y in coords:
            objects.append({'id':name,'type':'cylinder','category':'unknown','object_type':'buoy','centre':gps(x,y),'radius_m':.2,'height_m':1})
        m={'schema_version':3,'source':'live','geographic_reference':ref,'buoys':objects,'obstacles':[]}
        d={'geometry_version':2,'planner_task':'channel' if channel else 'slalom','task':'custom','start':gps(-6,0),'finish':gps(26+4.5*3/math.sqrt(10),6+4.5/math.sqrt(10)) if channel else gps(30,5),
           'speed_m_s':.5,'clearance_m':.5,'preferred_buffer_m':.5,'finish_radius_m':.5,'sizes_confirmed':True,'course_confirmed':True,
           'direction':[math.cos(angle),math.sin(angle)],'planning_area':[gps(x,y) for x,y in [(-12,-15),(40,-15),(40,25),(-12,25)]],
           'attempt':{'mode':'full','start_source':'manual'},'passages':[],'waypoints':[]}
        if channel:
            d['channel_chains']={'left':['l0','l1','l2'],'right':['r0','r1','r2']}
        else:
            d['passages']=[{'id':'gate_a','kind':'gate','red':'a','green':'b'}, {'id':'turn','kind':'turn','buoy':'t','side':'left'}, {'id':'gate_b','kind':'gate','red':'c','green':'d'}]
        return m,d,gps

    def test_rotation_translation_and_staggered_local_passages(self):
        for angle in (0,.47,1.93):
            m,d,gps=self.fixture(angle,(17,-8))
            c=Course(m,d)
            self.assertNotEqual(c.draft['passages'][0]['direction'],c.draft['passages'][-1]['direction'])
            result=generate(m,d,max_seconds=15)
            self.assertTrue(result['success'],result)
            self.assertEqual(result['draft']['clearance_m'],.5)
            self.assertNotIn('entry',result['draft'])

    def test_curved_unequal_chains_include_all_vertices(self):
        for angle in (0,.63):
            m,d,_=self.fixture(angle,channel=True)
            r=resolve_geometry(m,d)
            self.assertEqual(len(r['channel']),6)
            self.assertGreater(len(r['derived_sections']),3)
            result=generate(m,d,max_seconds=15)
            self.assertTrue(result['success'],result)

    def test_crossing_chains_and_invalid_polygon_rejected(self):
        m,d,_=self.fixture(channel=True)
        d['channel_chains']['right'].reverse()
        with self.assertRaisesRegex(ValueError,'cross|self-intersect'):
            resolve_geometry(m,d)
        m,d,_=self.fixture(channel=True)
        d['channel']=[m['buoys'][i]['centre'] for i in (0,5,2,3)]
        with self.assertRaises(ValueError):resolve_geometry(m,d)

    def test_remaining_requires_explicit_confirmation_and_preserves_setup(self):
        m,d,gps=self.fixture()
        original=deepcopy(d['passages'])
        d['attempt'].update(mode='remaining',first_section=1)
        self.assertFalse(generate(m,d)['success'])
        d['attempt']['selection_confirmed']=True
        resolved=resolve_geometry(m,d)
        self.assertEqual(resolved['excluded_sections'],['gate_a'])
        self.assertEqual(d['passages'],original)
        self.assertTrue(resolved['partial_attempt'])
        d['start']=gps(-10,-10)
        self.assertIsNone(remaining_suggestion(m,d))

    def test_inside_channel_activates_containment_and_exclusion_rejected(self):
        m,d,gps=self.fixture(channel=True)
        d['start']=gps(5,0)
        c=Course(m,d)
        self.assertEqual(c.initial_progress,1)
        self.assertIsNone(c.edge(to_local(d['start'],c.reference),to_local(gps(6,15),c.reference),c.initial_progress))
        d['start']=gps(5,5.8)
        with self.assertRaisesRegex(ValueError,'boundary exclusion'):Course(m,d)

    def test_exit_crosses_actual_last_gate_before_outside_finish(self):
        from shared.clearance import validate_route
        from shared.course import dot,sub
        for angle in (0,.63):
            with self.subTest(angle=angle):
                m,d,gps=self.fixture(angle,channel=True)
                old=Course(m,d)
                centre=to_local(old.draft['derived_sections'][-1]['centre'],old.reference)
                forward=old.planes[-1][1]
                d['finish']=to_gps(*(centre[i]+3*forward[i] for i in (0,1)),old.reference)
                c=Course(m,d)
                self.assertLess(math.dist(c.planes[-1][0],centre),1e-6)
                result=generate(m,d,max_seconds=15)
                self.assertTrue(result['success'],result)
                self.assertTrue(validate_route(m,result['draft'])['valid'])
                before=tuple(centre[i]-2*forward[i] for i in (0,1))
                finish=to_local(d['finish'],c.reference)
                self.assertEqual(c.edge(before,finish,len(c.planes)-1),len(c.planes))
                side=tuple(before[i]+10*c.planes[-1][2][i] for i in (0,1))
                self.assertIsNone(c.edge(before,side,len(c.planes)-1))
                self.assertGreater(dot(sub(finish,centre),forward),d['clearance_m']+d['finish_radius_m'])

    def test_exit_finish_needs_room_and_partial_cannot_skip_last_gate(self):
        m,d,gps=self.fixture(channel=True)
        c=Course(m,d)
        centre=to_local(c.draft['derived_sections'][-1]['centre'],c.reference)
        forward=c.planes[-1][1]
        d['finish']=to_gps(*(centre[i]+.2*forward[i] for i in (0,1)),c.reference)
        with self.assertRaisesRegex(ValueError,'Channel finish must be beyond'):Course(m,d)
        d['finish']=to_gps(*(centre[i]+3*forward[i] for i in (0,1)),c.reference)
        d['start']=gps(23,5)
        d['attempt'].update(mode='remaining',first_section=len(c.draft['passages'])-1,selection_confirmed=True)
        partial=Course(m,d)
        self.assertEqual(partial.initial_progress,0)
        result=generate(m,d,max_seconds=15)
        self.assertTrue(result['success'],result)

    def test_old_inside_channel_finish_is_rejected_and_cannot_restore_saved_setup(self):
        m,d,gps=self.fixture(channel=True)
        with tempfile.TemporaryDirectory() as directory:
            w=Workspace(directory)
            saved=w.edit({'map':m,'draft':d})
            for confirmed in (False,True):
                stale=deepcopy(d)
                stale.update(finish=gps(24.86,5.62),course_confirmed=confirmed)
                result=generate(m,stale,max_seconds=1)
                self.assertFalse(result['success'])
                if confirmed:
                    self.assertIn('Channel finish must be beyond',result['diagnostics'][0])
                self.assertNotIn('draft',result)
                with self.assertRaisesRegex(ValueError,'Channel finish must be beyond'):
                    w.edit({'draft':stale,'course':{'channel':{'finish':stale['finish']}}})
                self.assertEqual(w.read(),saved)

    def test_extended_channel_allows_outside_approach_through_beginning(self):
        for angle in (0,.63):
            with self.subTest(angle=angle):
                m,d,gps=self.fixture(angle,channel=True)
                d['channel']=[gps(x,y) for x,y in [(-4,6),(12,6),(24,12),(28,0),(14,-6),(-4,-6)]]
                c=Course(m,d)
                # Cross the reviewed cap and its side upstream of the buoy pair.
                for a,b in [((-4.2,0),(-3.8,0)),((-2,6.2),(-2,5.8))]:
                    self.assertEqual(c.edge(to_local(gps(*a),c.reference),to_local(gps(*b),c.reference),0),0)
                # The same side crossing downstream remains forbidden.
                self.assertIsNone(c.edge(to_local(gps(6,6.2),c.reference),to_local(gps(6,5.8),c.reference),0))
                d['start']=gps(-8,10)
                result=generate(m,d,max_seconds=15)
                self.assertTrue(result['success'],result)
                self.assertEqual(result['draft']['attempt']['initial_progress'],0)
                self.assertFalse(result['draft']['attempt']['started_inside_channel'])
                self.assertEqual(result['draft']['channel'],d['channel'])

    def test_finite_planes_do_not_block_unrelated_crossings(self):
        m,d,gps=self.fixture()
        c=Course(m,d)
        # Past the first gate, crossing its extended plane far outside its opening
        # does not count as a reverse crossing.
        self.assertEqual(c.edge(to_local(gps(1,14),c.reference),to_local(gps(-1,14),c.reference),1),1)
        self.assertIsNone(c.edge(to_local(gps(1,0),c.reference),to_local(gps(-1,0),c.reference),1))

    def test_live_capture_staleness_and_partial_movement(self):
        _,d,gps=self.fixture();d['attempt']['start_source']='live'
        for status in (None,{'position':gps(1,0),'position_age_s':4,'heartbeat_age_s':0}, {'position':gps(1,0),'position_age_s':0,'heartbeat_age_s':float('nan')}):
            with self.assertRaises(ValueError):capture_start(d,status)
        captured=capture_start(d,{'position':gps(2,0),'position_age_s':.1,'heartbeat_age_s':.2})
        self.assertEqual(captured['start'],gps(2,0))
        self.assertIn('captured_at',captured['attempt'])
        captured['attempt'].update(mode='remaining',selection_confirmed=True,selection_position=gps(0,0))
        with self.assertRaisesRegex(ValueError,'moved'):check_remaining_snapshot(self.fixture()[0],captured)

    def test_workspace_migration_backups_routes_manual_queue_and_revokes(self):
        from gcs.app.imports import point_map
        m,d,_=self.fixture();d.pop('geometry_version')
        m=point_map(m)
        manual={'task':'custom','waypoints':[d['finish']]}
        old={'map':m,'draft':d,'tasks':{'slalom':d,'manual':manual},'course':{'slalom':deepcopy(d)},'approval':{'old':True}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'workspace.json';path.write_text(json.dumps(old))
            w=Workspace(directory);state=w.read()
            self.assertIsNone(state['approval']);self.assertEqual(state['tasks']['manual'],manual)
            self.assertEqual(state['draft']['waypoints'],d['waypoints'])
            self.assertFalse(state['draft']['course_confirmed'])
            self.assertNotIn('attempt',state['course']['slalom'])
            backups=list(Path(directory).glob('workspace-before-general-course-*'))
            self.assertEqual(len(backups),1);self.assertEqual(json.loads(backups[0].read_text()),old)
            Workspace(directory);self.assertEqual(len(list(Path(directory).glob('workspace-before-general-course-*'))),1)


    def test_remaining_channel_generation_inside_and_outside(self):
        for start in ((-6,0),(15,1)):
            m,d,gps=self.fixture(channel=True)
            d['start']=gps(*start)
            d['attempt'].update(mode='remaining',first_section=1 if start[0]<0 else 2,selection_confirmed=True)
            result=generate(m,d,max_seconds=15)
            self.assertTrue(result['success'],result)
            self.assertEqual(result['draft']['excluded_sections'],['section_1'] if start[0]<0 else ['section_1','section_2'])
            self.assertEqual(d['channel_chains'],result['draft']['channel_chains'])

    def test_approved_channel_progress_cannot_be_silently_changed_by_motion(self):
        m,d,gps=self.fixture(channel=True)
        d['start']=gps(5,0)
        result=generate(m,d,max_seconds=15)
        self.assertTrue(result['success'],result)
        changed=deepcopy(result['draft']);changed['start']=gps(-4,0)
        with self.assertRaisesRegex(ValueError,'changes selected task progress'):Course(m,changed)

    def test_concave_notch_in_reviewed_boundary_rejects_section(self):
        from shared.task_geometry import segment_within
        polygon=[(0,0),(10,0),(10,10),(6,10),(6,4),(4,4),(4,10),(0,10)]
        self.assertFalse(segment_within((2,8),(8,8),polygon))
        self.assertTrue(segment_within((2,2),(8,2),polygon))


    def test_general_migration_preserves_active_manual_approval_for_point_map(self):
        from gcs.app.imports import point_map
        m,d,_=self.fixture();d.pop('geometry_version')
        m=point_map(m)
        manual={'task':'custom','waypoints':[d['finish']]}
        old={'map':m,'draft':manual,'tasks':{'slalom':d,'manual':manual},'course':{},'approval':{'manual':True}}
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'workspace.json').write_text(json.dumps(old))
            state=Workspace(directory).read()
            self.assertEqual(state['approval'],old['approval'])
            self.assertEqual(state['draft'],manual)
            self.assertFalse(state['tasks']['slalom']['course_confirmed'])


    def test_short_first_channel_interval_keeps_all_reviewed_points(self):
        m,d,gps=self.fixture(channel=True)
        m['buoys'][1]['centre']=gps(1.2,6)
        result=generate(m,d,max_seconds=15)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(result['draft']['derived_sections']),4)

    def test_extended_reviewed_water_allows_dense_end_sections(self):
        m,d,gps=self.fixture(channel=True)
        # Add a close last observation on both boundary chains and explicitly
        # review water beyond them so every crossing and the finish fit.
        for side,old,xy in [('left','l2',(23,11.5)),('right','r2',(27,-3/7))]:
            obj=deepcopy(next(o for o in m['buoys'] if o['id']==old))
            obj.update(id=side+'_near_end',centre=gps(*xy));m['buoys'].append(obj)
            d['channel_chains'][side].insert(-1,obj['id'])
        direction=(.948683298,.316227766)
        d['channel']=[gps(x,y) for x,y in [(0,6),(12,6),(24,12),(24+4*direction[0],12+4*direction[1]),(28+4*direction[0],4*direction[1]),(28,0),(14,-6),(0,-6)]]
        d['finish']=gps(26+1.5*direction[0],6+1.5*direction[1])
        result=generate(m,d,max_seconds=15)
        self.assertTrue(result['success'],result)


    def test_rotated_full_map_coalesces_roundtrip_fraction_duplicates(self):
        from gcs.app.course_setup import prepare_task
        m=json.loads((Path(__file__).resolve().parents[1]/'examples/competition-gps-map.json').read_text())
        ref=m['geographic_reference'];angle=.47
        for obj in [*m['buoys'],*m['obstacles']]:
            x,y=to_local(obj['centre'],ref)
            obj['centre']=to_gps(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle),ref)
        d=prepare_task(m,'channel',{'clearance_m':1.5})['draft']
        self.assertEqual(len(Course(m,d).planes),3)

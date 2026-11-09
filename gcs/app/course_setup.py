"""Reviewable task setup derived from imported labels and geometry, never truth."""
from copy import deepcopy
import math
import re
from shared.geometry import to_local, to_gps, finite
from shared.course import gap
from shared.avoidance import zones


def prepare_task(object_map, task, settings=None, assignments=None):
    if task not in ('gate','slalom','channel'):
        raise ValueError('select gate, slalom or channel')
    settings=settings or {}
    ref=object_map['geographic_reference']
    objects=[*object_map['buoys'],*object_map.get('obstacles',[])]
    points={o['id']:to_local(o['centre'],ref) for o in objects}
    required=finite(settings.get('clearance_m',1.8))
    finish_radius=finite(settings.get('finish_radius_m',1))
    draft={'task':'custom','planner_task':task,'geometry_version':2,'waypoints':[],
           'attempt':{'mode':'full','start_source':'live'},
           'start':deepcopy(settings.get('start') or object_map.get('start_pose',{}).get('position') or ref),
           'speed_m_s':settings.get('speed_m_s',.5),'clearance_m':required,
           'preferred_buffer_m':settings.get('preferred_buffer_m',required),'finish_radius_m':finish_radius,
           'sizes_confirmed':settings.get('sizes_confirmed',False),'course_confirmed':False,'passages':[]}
    if settings.get('tower_avoidance') is not None:
        draft['tower_avoidance']=deepcopy(settings['tower_avoidance'])
    notes=[]
    def gps(p):return to_gps(*p,ref)
    if task in ('gate','slalom'):
        candidates=[o for o in object_map['buoys'] if o.get('task') in ('dodge','slalom','gate') or 'gate_' in o['id'] or re.search(r'(^|_)turn_[0-9]+',o['id'])]
        pairs=[]
        for red in candidates:
            if red.get('category')!='red' or 'gate' not in red['id']:continue
            green=next((o for o in candidates if o.get('category')=='green' and o['id'].rsplit('_',1)[0]==red['id'].rsplit('_',1)[0]),None)
            if green:
                pairs.append((red,green))
        pairs.sort(key=lambda pair:pair[0]['id'])
        turns=[]
        if assignments:
            ids={o['id']:o for o in objects}
            pairs=[tuple(ids[assignments[f'slalom.{gate}.{colour}']] for colour in ('red','green')) for gate in (('entrance','exit') if task=='slalom' else ('entrance',))]
            turns=[ids[assignments[f'slalom.turn.{i}']] for i in range(1,5)] if task=='slalom' else []
        if not pairs:
            return {'draft':draft,'diagnostics':['No labeled gate assignment found. Select the gate objects and direction on the map.'],'ready':False}
        first=pairs[0]; a,b=[points[o['id']] for o in first]
        tangent=(b[0]-a[0],b[1]-a[1]); width=math.hypot(*tangent)
        direction=(tangent[1]/width,-tangent[0]/width)
        centre=lambda pair:tuple(sum(points[o['id']][i] for o in pair)/2 for i in (0,1))
        if len(pairs)>1:
            delta=tuple(centre(pairs[-1])[i]-centre(first)[i] for i in (0,1))
            if sum(delta[i]*direction[i]for i in (0,1))<0:direction=tuple(-v for v in direction)
        origin=centre(first); end=centre(pairs[-1]) if task=='slalom' else origin
        passage=lambda pair,index:{'id':f'gate_{index}','kind':'gate','red':pair[0]['id'],'green':pair[1]['id']}
        passages=[passage(first,1)]
        if task=='slalom':
            if not assignments:
                turns=sorted((o for o in candidates if re.search(r'(^|_)turn_[0-9]+',o['id'])),key=lambda o:int(re.search(r'turn_([0-9]+)',o['id']).group(1)))
            passages.extend({'id':f'turn_{i+1}','kind':'turn','buoy':o['id'],'side':'left' if o.get('category')=='red' else 'right' if o.get('category')=='green' else None}for i,o in enumerate(turns))
            if len(pairs)>1:passages.append(passage(pairs[-1],2))
        draft['passages']=passages
        for red,green in (pairs if task=='slalom' else pairs[:1]):
            opening=math.dist(points[red['id']],points[green['id']])-red.get('radius_m',0)-green.get('radius_m',0)
            needed=sum(zones(obj,draft)[0] for obj in (red,green))
            if opening<needed:
                notes.append(f'{red["id"]}: opening {opening:.2f} m; hard buffers need {needed:.2f} m. Review the buffer allowance or opening; they have not been reduced.')
        entry=tuple(origin[i]-3*direction[i]for i in (0,1))
        exit=tuple(end[i]+1.5*direction[i]for i in (0,1))
        draft['direction']=list(direction)
    else:
        boundary=[o for o in object_map['buoys'] if o.get('task') in ('evade','channel')]
        chains=[]
        for label in ('left','right'):
            chain=sorted((o for o in boundary if f'_{label}_' in o['id']),key=lambda o:o['id'])
            chains.append(chain)
        if assignments:
            ids={o['id']:o for o in objects}
            chains=[[ids[assignments[f'channel.{colour}.{i}']] for i in range(1,4)] for colour in ('red','green')]
        if any(len(c)<2 for c in chains):
            return {'draft':draft,'diagnostics':['Channel boundaries need operator assignment. Draw its permitted area and choose entry/exit.'],'ready':False}
        midpoint=lambda index:tuple(sum(points[c[index]['id']][i]for c in chains)/2 for i in (0,1))
        origin,end=midpoint(0),midpoint(-1)
        delta=tuple(end[i]-origin[i]for i in (0,1));length=math.hypot(*delta)
        direction=tuple(v/length for v in delta)
        entry=tuple(origin[i]-direction[i]for i in (0,1));exit=tuple(end[i]+1.5*direction[i]for i in (0,1))
        polygon=[points[o['id']] for o in chains[0]]+[points[o['id']] for o in reversed(chains[1])]
        draft.update(direction=list(direction),channel=[gps(p) for p in polygon],
                     channel_chains={name:[o['id'] for o in c] for name,c in zip(('left','right'),chains)})
    finish_direction=direction
    if task=='slalom' and assignments:
        a,b=[points[o['id']] for o in pairs[-1]]
        tangent=(b[0]-a[0],b[1]-a[1]);width=math.hypot(*tangent)
        finish_direction=(tangent[1]/width,-tangent[0]/width)
        delta=tuple(end[i]-points[turns[-1]['id']][i] for i in (0,1))
        if sum(delta[i]*finish_direction[i] for i in (0,1))<0:
            finish_direction=tuple(-v for v in finish_direction)
    if task=='channel':
        # Stop beyond the actual last pair, along its local forward normal.
        a,b=[points[c[-1]['id']] for c in chains]
        tangent=(b[0]-a[0],b[1]-a[1]);width=math.hypot(*tangent)
        if width<1e-6:
            raise ValueError('final channel gate needs two distinct boundary points')
        finish_direction=(tangent[1]/width,-tangent[0]/width)
        delta=tuple(midpoint(-1)[i]-midpoint(-2)[i] for i in (0,1))
        if sum(delta[i]*finish_direction[i] for i in (0,1))<0:
            finish_direction=tuple(-v for v in finish_direction)
    left=(-finish_direction[1],finish_direction[0]);finish=None
    base=max(4.5,required+finish_radius+.2) if task=='channel' else 4.5
    for distance in (base,base+2,base+4):
        for lateral in (0,required+finish_radius+1,-required-finish_radius-1):
            candidate=tuple(end[i]+distance*finish_direction[i]+lateral*left[i]for i in (0,1))
            if all(gap(o,candidate,candidate,ref)>=(zones(o,draft)[0] if task=='channel' else required)+finish_radius+.05 for o in objects):
                finish=candidate;break
        if finish is not None:break
    if finish is None:
        finish=tuple(end[i]+base*finish_direction[i]for i in (0,1));notes.append('Choose a clear finish area; nearby objects block the suggested finish.')
    all_points=[*points.values(),to_local(draft['start'],ref),entry,exit,finish]
    padding=required+finish_radius+5
    xmin=min(p[0]for p in all_points)-padding;xmax=max(p[0]for p in all_points)+padding
    ymin=min(p[1]for p in all_points)-padding;ymax=max(p[1]for p in all_points)+padding
    draft.update(entry=gps(entry),exit=gps(exit),finish=gps(finish),entry_radius_m=1,exit_radius_m=1,
                 planning_area=[gps(p)for p in [(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax)]])
    draft.pop('entry',None);draft.pop('exit',None)
    from shared.task_geometry import resolve_geometry
    try:
        draft['derived_sections']=resolve_geometry(object_map,draft)['derived_sections']
    except (ValueError,KeyError) as error:
        notes.append(str(error))
    if assignments:
        # Recognition supplies roles and a finish suggestion, never an approved
        # water boundary. The operator draws/reviews the shared planning area.
        draft['planning_area']=[]
        notes.append('Compiled assignment template. Review local directions, finish, water and settings; confirm this card separately.')
    return {'draft':draft,'diagnostics':notes,'ready':True,'recognition_source':'accepted' if assignments else 'manual_or_labels'}

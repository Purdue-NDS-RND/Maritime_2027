"""Deterministic bounded grid A*, with ordered passage and heading state."""
from copy import deepcopy
import heapq
import math
import re
import time
from shared.geometry import to_local, to_gps, finite
from shared.course import Course, gap, dot, sub, contained
from shared.clearance import validate_route

STEPS=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))


def entry_fits_channel(course):
    """Prove impossible entry windows against convex channel inset edges.

    Concave channels keep the normal search/segment validation path.
    """
    poly=course.channel
    if not poly:
        return True
    cross=lambda a,b:a[0]*b[1]-a[1]*b[0]
    edges=[sub(b,a) for a,b in zip(poly,poly[1:]+poly[:1])]
    area=sum(cross(a,b) for a,b in zip(poly,poly[1:]+poly[:1]))
    sign=1 if area>0 else -1
    if any(sign*cross(a,b)<-1e-7 for a,b in zip(edges,edges[1:]+edges[:1])):
        return True
    origin,_,left,low,high,_=course.planes[0]
    for a,edge in zip(poly,edges):
        base=sign*cross(edge,sub(origin,a))
        slope=sign*cross(edge,left)
        needed=course.required*math.hypot(*edge)
        if abs(slope)<1e-10:
            if base<needed-1e-7:
                return False
        elif slope>0:
            low=max(low,(needed-base)/slope)
        else:
            high=min(high,(needed-base)/slope)
        if low>high+1e-7:
            return False
    return True


def suggest(object_map, direction):
    dx,dy=map(finite,direction); length=math.hypot(dx,dy)
    if length<1e-6:
        raise ValueError('select travel direction first')
    forward=(dx/length,dy/length); left=(-forward[1],forward[0])
    ref=object_map['geographic_reference']; objects=object_map['buoys']
    candidates=[]
    for i,a in enumerate(objects):
        for b in objects[i+1:]:
            delta=sub(to_local(b['centre'],ref),to_local(a['centre'],ref))
            width=math.hypot(*delta)
            if width and abs(dot(delta,forward))<.35*width:
                candidates.append({'kind':'gate','id':f'pair_{len(candidates)+1}','red':a['id'],'green':b['id'],
                                   'direction':direction,'width_m':width,'confirmed':False})
    candidates.sort(key=lambda p:(p['width_m'],p['red'],p['green']))
    ordered=sorted(objects,key=lambda o:dot(to_local(o['centre'],ref),forward))
    labeled_turns=[o for o in ordered if re.search(r'(^|_)turn_[0-9]+',o['id'].lower()) or o.get('course_role')=='slalom_turn']
    turns=[{'id':f'turn_{i+1}','kind':'turn','buoy':o['id'],
            'side': 'left' if o.get('category')=='red' else 'right' if o.get('category')=='green' else None,
            'direction':direction,'confirmed':False} for i,o in enumerate(labeled_turns or ordered)]
    labeled_channel=[o for o in ordered if o.get('task') in ('evade','channel') or 'channel' in o['id'].lower()]
    channel_objects=labeled_channel or [o for o in ordered if o.get('object_type')!='detector']
    if not channel_objects:
        channel_objects=ordered
    centre=sum(dot(to_local(o['centre'],ref),left) for o in channel_objects)/len(channel_objects)
    chains={name:[o['id'] for o in channel_objects if (dot(to_local(o['centre'],ref),left)>=centre)==positive]
            for name,positive in [('left',True),('right',False)]}
    return {'gate_candidates':candidates,'slalom':turns,'channel_chains':chains,'confirmed':False,
            'diagnostics':['Geometry candidates may overlap tasks. Assign objects and confirm every role; unknown passing sides require operator input.']}


def generate(object_map, draft, resolutions=(.25,.10,.05), max_expansions=250000, max_seconds=60):
    deadline=time.monotonic()+max_seconds
    draft=deepcopy(draft)
    preferred=finite(draft.get('preferred_buffer_m',draft['clearance_m']))
    if preferred<finite(draft['clearance_m']):
        raise ValueError('preferred buffer must be at least required buffer')
    if not draft.get('planner_task') or not draft.get('sizes_confirmed') or not draft.get('course_confirmed') or not draft.get('planning_area') or not draft.get('entry') or not draft.get('exit'):
        return {'success':False,'diagnostics':['incomplete course assignments']}
    try:
        course=Course(object_map,draft)
    except (KeyError,ValueError) as error:
        return {'success':False,'diagnostics':[str(error)]}
    # An interval union on the entry plane can prove a blocked approach for
    # circular obstacles. Other geometric failures remain search exhaustion.
    origin,forward,left,low,high,_=course.planes[0]
    intervals=[]
    for obj in course.objects:
        if obj['type']!='cylinder':
            continue
        relative=sub(to_local(obj['centre'],course.reference),origin)
        along=dot(relative,forward); radius=obj['radius_m']+course.required
        if abs(along)<radius:
            half=math.sqrt(radius*radius-along*along); lateral=dot(relative,left)
            intervals.append((lateral-half,lateral+half))
    covered=low
    for a,b in sorted(intervals):
        if a>covered+1e-7:
            break
        covered=max(covered,b)
    if covered>=high:
        return {'success':False,'diagnostics':['obstructed approach: confirmed entry window is blocked at required buffer']}
    if draft['planner_task']=='channel' and not draft.get('channel'):
        return {'success':False,'diagnostics':['incomplete channel boundary assignments']}
    if draft['planner_task']=='channel' and not entry_fits_channel(course):
        return {'success':False,'diagnostics':['Channel entry window is too close to the permitted channel boundary for the required buffer. Move Entry inside the channel with enough room on each side; use Use live boat position to change only the attempt start.']}
    ref=course.reference; start=to_local(draft['start'],ref); finish=to_local(draft['finish'],ref)
    if course.clearance(start,start)<course.required or any(not contained(start,start,p,course.required) for p in course.polygons):
        return {'success':False,'diagnostics':['obstructed approach: unsafe planning start']}
    if course.clearance(finish,finish)<course.required+draft['finish_radius_m'] or any(not contained(finish,finish,p,course.required+draft['finish_radius_m']) for p in [*course.polygons,*([course.channel] if course.channel else [])]):
        return {'success':False,'diagnostics':['unsafe finish area']}
    polygon=course.polygons[0]; xmin=min(p[0] for p in polygon); xmax=max(p[0] for p in polygon)
    ymin=min(p[1] for p in polygon); ymax=max(p[1] for p in polygon)
    detectors=[o for o in course.objects if o.get('object_type')=='detector']
    attempts=[]
    for spacing in resolutions:
        # Grid anchored at exact start; goal has a separately checked connection.
        initial=(0,0,0,-1); costs={initial:0}; parents={}; queue=[(course.heuristic(start,finish,0),0,initial)]; expanded=0; goal=None
        edge_cache={}
        def position(state):
            return start[0]+state[0]*spacing,start[1]+state[1]*spacing
        while queue and expanded<max_expansions:
            if time.monotonic()>=deadline:
                return {'success':False,'diagnostics':['Planning time limit reached; blockage is not proven. Review entry, boundaries and required buffer before retrying.'],
                        'attempts':attempts+[{'spacing_m':spacing,'expanded':expanded,'time_exhausted':True}]}
            _,cost,state=heapq.heappop(queue)
            if cost!=costs.get(state):
                continue
            expanded+=1; a=position(state); progress=state[2]
            if math.dist(a,finish)<=spacing*1.5 and course.edge(a,finish,progress)==len(course.planes):
                goal=state; break
            for heading,(dx,dy) in enumerate(STEPS):
                x,y=state[0]+dx,state[1]+dy; b=(start[0]+x*spacing,start[1]+y*spacing)
                if not xmin<=b[0]<=xmax or not ymin<=b[1]<=ymax:
                    continue
                key=(state[0],state[1],x,y,progress)
                if key not in edge_cache:
                    next_progress=course.edge(a,b,progress)
                    clearance=course.clearance(a,b) if next_progress is not None else 0
                    detector=sum(1/(1+max(0,gap(o,a,b,ref))) for o in detectors)/max(1,len(detectors)) if next_progress is not None else 0
                    edge_cache[key]=(next_progress,clearance,detector)
                next_progress,clearance,detector=edge_cache[key]
                if next_progress is None:
                    continue
                distance=math.dist(a,b)
                shortfall=max(0,preferred-clearance)/max(preferred,1e-6)
                turn=0 if state[3]<0 else min((heading-state[3])%8,(state[3]-heading)%8)*.02
                new_cost=cost+distance*(1+4*shortfall+min(1,detector))+turn
                child=(x,y,next_progress,heading)
                if new_cost<costs.get(child,math.inf)-1e-10:
                    costs[child]=new_cost; parents[child]=state
                    heapq.heappush(queue,(new_cost+course.heuristic(b,finish,next_progress),new_cost,child))
        attempts.append({'spacing_m':spacing,'expanded':expanded,'budget_exhausted':expanded>=max_expansions})
        if goal is None:
            continue
        path=[finish]; state=goal
        while state!=initial:
            path.append(position(state)); state=parents[state]
        path.append(start); path.reverse()
        # Greedy visibility simplification also preserves passage progress.
        simplified=[start]; progress=0; i=0
        while i<len(path)-1:
            if time.monotonic()>=deadline:
                return {'success':False,'diagnostics':['Planning time limit reached while simplifying the route; no draft was generated.'], 'attempts':attempts}
            chosen=i+1
            # Preserve attained preferred clearance on removed edges; no hidden shortcut penalty.
            baseline=course.clearance(path[i],path[i+1])
            for j in range(len(path)-1,i,-1):
                candidate=course.edge(path[i],path[j],progress)
                expected=progress
                for k in range(i,j):
                    expected=course.edge(path[k],path[k+1],expected)
                    if expected is None:
                        break
                if candidate is not None and candidate==expected and course.clearance(path[i],path[j])>=min(preferred,baseline)-1e-7:
                    chosen=j; break
            progress=course.edge(path[i],path[chosen],progress)
            simplified.append(path[chosen]); i=chosen
        draft['waypoints']=[to_gps(*p,ref) for p in simplified[1:]]
        result=validate_route(object_map,draft)
        if result['valid']:
            return {'success':True,'draft':draft,'validation':result,'attempts':attempts,'diagnostics':[]}
        return {'success':False,'diagnostics':[e['reason'] for e in result['errors']],'attempts':attempts}
    return {'success':False,'diagnostics':['search exhaustion: no route at supported resolutions; blockage is not proven'], 'attempts':attempts}

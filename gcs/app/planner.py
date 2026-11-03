"""Deterministic bounded grid A*, with ordered passage and heading state."""
from copy import deepcopy
import heapq
import math
import re
import time
from shared.geometry import to_local, to_gps, finite
from shared.course import Course, gap, dot, sub, contained
from shared.clearance import validate_route
from shared.avoidance import zones

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


def _generate(object_map, draft, resolutions=(.25,.10,.05), max_expansions=250000, max_seconds=60):
    deadline=time.monotonic()+max_seconds
    draft=deepcopy(draft)
    preferred=finite(draft.get('preferred_buffer_m',draft['clearance_m']))
    if preferred<finite(draft['clearance_m']):
        raise ValueError('preferred buffer must be at least required buffer')
    if not draft.get('planner_task') or not draft.get('sizes_confirmed') or not draft.get('course_confirmed') or not draft.get('planning_area') or (draft.get('geometry_version')!=2 and (not draft.get('entry') or not draft.get('exit'))):
        return {'success':False,'diagnostics':['incomplete course assignments']}
    course_input=deepcopy(draft)
    try:
        course=Course(object_map,draft)
        if not course.planes:
            raise ValueError('missing passage assignments')
        draft=deepcopy(course.draft)
        if course.general:
            course_input.setdefault('attempt',{})['initial_progress']=course.initial_progress
            course_input['attempt']['started_inside_channel']=course.start_inside_channel
    except (KeyError,ValueError) as error:
        return {'success':False,'diagnostics':[str(error)]}
    # An interval union on the entry plane can prove a blocked approach for
    # circular obstacles. Other geometric failures remain search exhaustion.
    origin,forward,left,low,high,_=course.planes[0]
    intervals=[]
    for obj in course.objects:
        if obj['type'] not in ('point','cylinder'):
            continue
        relative=sub(to_local(obj['centre'],course.reference),origin)
        along=dot(relative,forward); radius=obj.get('radius_m',0)+zones(obj,draft)[0]
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
    if not course.general and draft['planner_task']=='channel' and not entry_fits_channel(course):
        return {'success':False,'diagnostics':['Channel entry window is too close to the permitted channel boundary for the required buffer. Move Entry inside the channel with enough room on each side; use Use live boat position to change only the attempt start.']}
    ref=course.reference; start=to_local(draft['start'],ref); finish=to_local(draft['finish'],ref)
    if course.clearance(start,start)<course.required or any(not contained(start,start,p,course.required) for p in course.polygons):
        conflicts=[o['id'] for o in course.objects if gap(o,start,start,ref)<zones(o,draft)[0]]
        return {'success':False,'diagnostics':['obstructed approach: unsafe planning start'+(': '+', '.join(conflicts) if conflicts else ' at planning boundary')],
                'errors':[{'code':'unsafe_start','reason':'Unsafe planning start','location':list(start),'objects':conflicts}]}
    if course.clearance(finish,finish)<course.required+draft['finish_radius_m'] or any(not contained(finish,finish,p,course.required+draft['finish_radius_m']) for p in [*course.polygons,*([course.channel] if course.channel else [])]):
        return {'success':False,'diagnostics':['unsafe finish area']}
    polygon=course.polygons[0]; xmin=min(p[0] for p in polygon); xmax=max(p[0] for p in polygon)
    ymin=min(p[1] for p in polygon); ymax=max(p[1] for p in polygon)
    detectors=[o for o in course.objects if o.get('object_type')=='detector']
    # Tower costs can make the straight-distance bound very weak over a large
    # map. Bounded weighted A* prioritizes a useful route within the same effort
    # budget; it does not claim a globally minimum-cost path.
    heuristic_weight=1
    heuristic_cache={}
    def estimate(point,progress):
        key=(*point,progress)
        if key not in heuristic_cache:
            length=course.heuristic(point,finish,progress)
            heuristic_cache[key]=heuristic_weight*length+course.tower_lower_bound(point,finish,length)
        return heuristic_cache[key]
    attempts=[]
    # If a broad soft zone exhausts the first preference search, increase
    # heuristic emphasis before spending effort on a finer grid. Hard checks
    # and the one shared deadline remain identical in every search.
    searches=[(spacing,weight) for spacing in resolutions for weight in ((4,8,16,32) if course.towers else (1,))]
    for spacing,heuristic_weight in searches:
        heuristic_cache.clear()
        # Grid anchored at exact start; goal has a separately checked connection.
        initial=(0,0,course.initial_progress,-1); costs={initial:0}; parents={}; queue=[(estimate(start,course.initial_progress),0,initial)]; expanded=0; goal=None
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
                    clearance=course.clearance(a,b,preference=True) if next_progress is not None else 0
                    detector=course.tower_cost(a,b) if course.tower_policy is not None else (sum(1/(1+max(0,gap(o,a,b,ref))) for o in detectors)/max(1,len(detectors)) if next_progress is not None else 0)
                    edge_cache[key]=(next_progress,clearance,detector)
                next_progress,clearance,detector=edge_cache[key]
                if next_progress is None:
                    continue
                distance=math.dist(a,b)
                shortfall=max(0,preferred-clearance)/max(preferred,1e-6)
                turn=0 if state[3]<0 else min((heading-state[3])%8,(state[3]-heading)%8)*.02
                new_cost=cost+distance*(1+4*shortfall+detector)+turn
                child=(x,y,next_progress,heading)
                if new_cost<costs.get(child,math.inf)-1e-10:
                    costs[child]=new_cost; parents[child]=state
                    heapq.heappush(queue,(new_cost+estimate(b,next_progress),new_cost,child))
        attempts.append({'spacing_m':spacing,'expanded':expanded,'heuristic_weight':heuristic_weight,'budget_exhausted':expanded>=max_expansions})
        if goal is None:
            continue
        path=[finish]; state=goal
        while state!=initial:
            path.append(position(state)); state=parents[state]
        path.append(start); path.reverse()
        # Greedy visibility simplification also preserves passage progress.
        path_progress=[course.initial_progress]
        for a,b in zip(path,path[1:]):
            if time.monotonic()>=deadline:
                return {'success':False,'diagnostics':['Planning time limit reached while simplifying the route; no draft was generated.'],'attempts':attempts}
            path_progress.append(course.edge(a,b,path_progress[-1]))
        prefix_cost=[0.0]
        for a,b in zip(path,path[1:]):
            if time.monotonic()>=deadline:
                return {'success':False,'diagnostics':['Planning time limit reached during cost preservation; no draft was generated.'],'attempts':attempts}
            prefix_cost.append(prefix_cost[-1]+course.travel_cost(a,b,preferred,deadline))
        simplified=[start]; progress=course.initial_progress; i=0
        while i<len(path)-1:
            if time.monotonic()>=deadline:
                return {'success':False,'diagnostics':['Planning time limit reached while simplifying the route; no draft was generated.'], 'attempts':attempts}
            chosen=i+1
            # Preserve attained preferred clearance on removed edges; no hidden shortcut penalty.
            baseline=course.clearance(path[i],path[i+1],preference=True)
            for j in range(len(path)-1,i,-1):
                if time.monotonic()>=deadline:
                    return {'success':False,'diagnostics':['Planning time limit reached while simplifying the route; no draft was generated.'],'attempts':attempts}
                candidate=course.edge(path[i],path[j],progress)
                expected=path_progress[j]
                if candidate is not None and candidate==expected and course.clearance(path[i],path[j],preference=True)>=min(preferred,baseline)-1e-7 and (not course.towers or course.travel_cost(path[i],path[j],preferred,deadline)<=prefix_cost[j]-prefix_cost[i]+1e-6):
                    chosen=j; break
            progress=course.edge(path[i],path[chosen],progress)
            simplified.append(path[chosen]); i=chosen
        derived=draft
        draft=deepcopy(course_input)
        draft['waypoints']=[to_gps(*p,ref) for p in simplified[1:]]
        draft.pop('planning_notice',None)
        if heuristic_weight>4:
            draft['planning_notice']='Avoidance optimization reached its initial search budget. This route satisfies hard zones; review soft-zone crossings because a better detour may exist.'
        for key in ('derived_sections','excluded_sections','partial_attempt'):
            if key in derived:
                draft[key]=derived[key]
        if course.general:
            from shared.task_geometry import setup_identity
            draft['generation_setup_sha256']=setup_identity(object_map,draft)
        draft.pop('generation_errors',None)
        result=validate_route(object_map,draft)
        if time.monotonic()>=deadline:
            return {'success':False,'diagnostics':['Planning time limit reached during final GPS validation; no draft was generated.'],'attempts':attempts}
        if result['valid']:
            draft['route_sections']=[]
            progress=course.initial_progress
            for i,(a,b) in enumerate(zip(simplified,simplified[1:])):
                next_progress=course.edge(a,b,progress)
                crossing=None
                if progress==0 and next_progress>0:
                    origin,forward,_,_,_,_=course.planes[0]
                    u,v=dot(sub(a,origin),forward),dot(sub(b,origin),forward)
                    if u<=0<v:
                        fraction=-u/(v-u)
                        crossing=tuple(a[k]+fraction*(b[k]-a[k]) for k in (0,1))
                        draft['route_sections'].append({'leg':i,'kind':'approach','start':to_gps(*a,ref),'end':to_gps(*crossing,ref)})
                draft['route_sections'].append({'leg':i,'kind':'task' if crossing or progress>0 else 'approach','start':to_gps(*(crossing or a),ref),'end':to_gps(*b,ref),'from_progress':progress,'to_progress':next_progress})
                progress=next_progress
            return {'success':True,'draft':draft,'validation':result,'attempts':attempts,'diagnostics':[]}
        return {'success':False,'diagnostics':[e['reason'] for e in result['errors']],'attempts':attempts}
    return {'success':False,'diagnostics':['search exhaustion: no route at supported resolutions; blockage is not proven'], 'attempts':attempts}


def generate(object_map, draft, *args, **kwargs):
    try:
        result=_generate(object_map,draft,*args,**kwargs)
    except (ValueError,KeyError,TypeError,TimeoutError) as error:
        result={'success':False,'diagnostics':[str(error)]}
    if not result['success'] and 'errors' not in result:
        reason='; '.join(result['diagnostics'])
        code='search_exhausted' if any(word in reason.lower() for word in ('exhaust','time limit')) else 'blocked' if any(word in reason.lower() for word in ('blocked','insufficient gate')) else 'invalid_setup'
        location=None; related=[]
        if 'start' in reason.lower():
            location=list(to_local(draft['start'],object_map['geographic_reference']))
        elif 'finish' in reason.lower():
            location=list(to_local(draft['finish'],object_map['geographic_reference']))
        for obj in [*object_map['buoys'],*object_map.get('obstacles',[])]:
            if obj['id'] in reason:
                location=list(to_local(obj['centre'],object_map['geographic_reference']));related.append(obj['id'])
        passage=None
        ids={o['id']:o for o in [*object_map['buoys'],*object_map.get('obstacles',[])]}
        for p in draft.get('passages',[]):
            if p.get('id') and p['id'] in reason:
                passage=p['id']
                objects=[ids[p[key]] for key in ('red','green','buoy') if p.get(key) in ids]
                if objects:
                    points=[to_local(o['centre'],object_map['geographic_reference']) for o in objects]
                    location=[sum(p[i] for p in points)/len(points) for i in (0,1)]
                    related.extend(o['id'] for o in objects)
        result['errors']=[{'code':code,'reason':reason,'location':location,'objects':sorted(set(related)),'passage':passage,'boundary':'channel' if 'channel' in reason.lower() else None}]
    return result

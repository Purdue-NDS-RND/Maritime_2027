"""Orientation-independent finite passages and bounded-course constraints."""
import math
from .geometry import finite, to_local, segment_distance


def dot(a, b):
    return a[0]*b[0]+a[1]*b[1]


def sub(a, b):
    return a[0]-b[0], a[1]-b[1]


def inside(p, polygon):
    hit = False
    for a,b in zip(polygon, polygon[1:]+polygon[:1]):
        if segment_distance(p,a,b) < 1e-8:
            return True
        if (a[1]>p[1]) != (b[1]>p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            hit = not hit
    return hit


def intersects(a,b,c,d):
    def cross(p,q,r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    return (max(min(a[0],b[0]),min(c[0],d[0])) <= min(max(a[0],b[0]),max(c[0],d[0]))
            and max(min(a[1],b[1]),min(c[1],d[1])) <= min(max(a[1],b[1]),max(c[1],d[1]))
            and cross(a,b,c)*cross(a,b,d)<=0 and cross(c,d,a)*cross(c,d,b)<=0)


def polygon_valid(poly):
    if len(poly)<3 or len(poly)>64 or any(math.dist(a,b)<1e-8 for a,b in zip(poly,poly[1:]+poly[:1])) or abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1])))<1e-6:
        return False
    edges=list(zip(poly,poly[1:]+poly[:1]))
    return all(not intersects(a,b,c,d) for i,(a,b) in enumerate(edges) for j,(c,d) in enumerate(edges)
               if j>i+1 and (i,j)!=(0,len(edges)-1))


def contained(a,b,poly,buffer=0):
    if not inside(a,poly) or not inside(b,poly):
        return False
    for c,d in zip(poly,poly[1:]+poly[:1]):
        if intersects(a,b,c,d):
            return False
        if min(segment_distance(a,c,d),segment_distance(b,c,d),segment_distance(c,a,b),segment_distance(d,a,b)) < buffer-1e-7:
            return False
    return True


def gap(obj,a,b,reference):
    if obj['type']=='cylinder':
        return segment_distance(to_local(obj['centre'],reference),a,b)-obj['radius_m']
    poly=[to_local(p,reference) for p in obj['footprint']]
    return polygon_gap(poly,a,b)


def polygon_gap(poly,a,b):
    if inside(a,poly) or inside(b,poly):
        return -1e-9
    result=math.inf
    for c,d in zip(poly,poly[1:]+poly[:1]):
        if intersects(a,b,c,d):
            return -1e-9
        result=min(result,segment_distance(a,c,d),segment_distance(b,c,d),segment_distance(c,a,b),segment_distance(d,a,b))
    return result


class Course:
    def __init__(self, object_map, draft):
        from .task_geometry import resolve_geometry
        draft=resolve_geometry(object_map,draft)
        self.draft=draft
        self.general=draft.get('geometry_version')==2
        self.reference=object_map['geographic_reference']
        self.required=finite(draft['clearance_m'])
        self.objects=[*object_map['buoys'],*object_map.get('obstacles',[])]
        ids={o['id']:o for o in self.objects}
        self.circles=[(to_local(o['centre'],self.reference),o['radius_m']) for o in self.objects if o['type']=='cylinder']
        self.footprints=[]
        for obj in self.objects:
            if obj['type']=='polygon':
                centre=to_local(obj['centre'],self.reference)
                polygon=[to_local(p,self.reference) for p in obj['footprint']]
                self.footprints.append((centre,max(math.dist(centre,p) for p in polygon),polygon))
        self.polygons=[]
        self.reviewed_channel=[to_local(p,self.reference) for p in draft.get('reviewed_channel',[])]
        self.access=[to_local(p,self.reference) for p in draft.get('channel_access',[])]
        self.channel=None
        self.start_inside_channel=False
        self.has_entry=bool(draft.get('planner_task') and draft.get('entry')) or bool(draft.get('channel_entrance'))
        self.initial_progress=0
        for key in ('planning_area','channel'):
            if key in draft:
                poly=[to_local(p,self.reference) for p in draft[key]]
                if not polygon_valid(poly):
                    raise ValueError('invalid '+key+' polygon')
                if key=='channel':
                    self.channel=poly
                else:
                    self.polygons.append(poly)
        self.planes=[]
        if draft.get('planner_task') and draft.get('entry'):
            dx,dy=map(finite,draft['direction']); length=math.hypot(dx,dy)
            if length<1e-6:
                raise ValueError('confirm nonzero travel direction')
            forward=(dx/length,dy/length); left=(-forward[1],forward[0])
            width=finite(draft.get('entry_radius_m',1))
            if width<=0:
                raise ValueError('entry radius must be positive')
            self.planes.append((to_local(draft['entry'],self.reference),forward,left,-width,width,'task_entry'))
        seen=set()
        for p in draft.get('passages',[]):
            if not isinstance(p.get('id'),str) or p['id'] in seen:
                raise ValueError('unique passage IDs required')
            seen.add(p['id'])
            direction=p.get('direction',draft.get('direction',[1,0]))
            dx,dy=map(finite,direction)
            length=math.hypot(dx,dy)
            if length<1e-6:
                raise ValueError('confirm nonzero travel direction')
            forward=(dx/length,dy/length); left=(-forward[1],forward[0])
            if p['kind']=='gate':
                first,second=ids[p['red']],ids[p['green']]
                if first==second or first['type']!='cylinder' or second['type']!='cylinder':
                    raise ValueError('gate requires two distinct circular objects')
                a,b=to_local(first['centre'],self.reference),to_local(second['centre'],self.reference)
                tangent=sub(b,a); width=math.hypot(*tangent)
                if width<1e-6:
                    raise ValueError('insufficient gate opening')
                left=(tangent[0]/width,tangent[1]/width)
                normal=(left[1],-left[0])
                if dot(normal,forward)<0:
                    normal=(-normal[0],-normal[1])
                if abs(dot(normal,forward))<.1:
                    raise ValueError('travel direction must cross gate')
                forward=normal
                origin=a; low=first['radius_m']+self.required; high=width-second['radius_m']-self.required
                if low>high:
                    raise ValueError('insufficient gate opening: '+p['id'])
            elif p['kind']=='section':
                origin=to_local(p['centre'],self.reference)
                width=finite(p['half_width_m'])
                low,high=-width+self.required,width-self.required
                if low>=high:
                    raise ValueError('blocked channel section: '+p['id'])
            elif p['kind']=='turn':
                obj=ids[p['buoy']]
                if obj['type']!='cylinder' or p.get('side') not in ('left','right'):
                    raise ValueError('turn requires buoy and passing side')
                origin=to_local(obj['centre'],self.reference)
                offset=obj['radius_m']+self.required
                low,high=(offset,math.inf) if p['side']=='left' else (-math.inf,-offset)
                if self.general and self.polygons:
                    projections=[dot(sub(v,origin),left) for v in self.polygons[0]]
                    low=max(low,min(projections)); high=min(high,max(projections))
            else:
                raise ValueError('unsupported passage kind')
            self.planes.append((origin,forward,left,low,high,p['id']))

        if draft.get('planner_task') and draft.get('exit'):
            dx,dy=map(finite,draft['direction']); length=math.hypot(dx,dy)
            if length<1e-6:
                raise ValueError('confirm nonzero travel direction')
            forward=(dx/length,dy/length); left=(-forward[1],forward[0])
            width=finite(draft.get('exit_radius_m',1))
            if width<=0:
                raise ValueError('exit radius must be positive')
            self.planes.append((to_local(draft['exit'],self.reference),forward,left,-width,width,'task_exit'))

        if self.general and self.channel:
            start=to_local(draft['start'],self.reference)
            if inside(start,self.channel):
                if not contained(start,start,self.channel,self.required):
                    raise ValueError('unsafe planning start: inside channel boundary exclusion buffer at '+str(list(start)))
                origin,forward,_,_,_,_=self.planes[0]
                self.start_inside_channel=True
                # The entrance may be omitted only when the start is in its
                # selected first cell. Later cells require the full return.
                next_plane=self.planes[1] if len(self.planes)>1 else None
                if next_plane is None or dot(sub(start,next_plane[0]),next_plane[1])<0:
                    self.initial_progress=1
                elif draft.get('attempt',{}).get('mode')=='remaining':
                    raise ValueError('start lies beyond the selected remaining channel section; review and confirm a later first section')
                elif not contained(origin,origin,self.channel,self.required):
                    raise ValueError('full-task return to the beginning conflicts with the channel start allowance; correct permitted water or explicitly confirm Remaining section')

        attempt=draft.get('attempt',{})
        if self.general and 'initial_progress' in attempt and (attempt['initial_progress']!=self.initial_progress or attempt.get('started_inside_channel')!=self.start_inside_channel):
            raise ValueError('actual position changes selected task progress or channel connection; review and generate a new attempt')

        self.windows=[]
        for origin,forward,left,low,high,_ in self.planes:
            if math.isfinite(low) and math.isfinite(high):
                self.windows.append((tuple(origin[i]+low*left[i] for i in (0,1)),tuple(origin[i]+high*left[i] for i in (0,1))))
            else:
                self.windows=[]
                break
        self.remaining_distance=[0.0]*len(self.windows)
        for i in range(len(self.windows)-2,-1,-1):
            a,b=self.windows[i];c,d=self.windows[i+1]
            distance=0 if intersects(a,b,c,d) else min(segment_distance(a,c,d),segment_distance(b,c,d),segment_distance(c,a,b),segment_distance(d,a,b))
            self.remaining_distance[i]=self.remaining_distance[i+1]+distance

    def clearance(self,a,b):
        minimum=min((segment_distance(centre,a,b)-radius for centre,radius in self.circles),default=math.inf)
        for centre,radius,polygon in self.footprints:
            if segment_distance(centre,a,b)-radius<minimum:
                minimum=min(minimum,polygon_gap(polygon,a,b))
        return minimum

    def edge(self,a,b,progress):
        if self.clearance(a,b)<self.required-1e-7 or any(not contained(a,b,p,self.required) for p in self.polygons):
            return None
        entered = not self.has_entry or progress>0 or self.start_inside_channel
        channel_start = a if entered else None
        if self.general and self.channel and not entered:
            # Outside approaches may enter only through the selected opening.
            access=self.access
            for c,d in zip(self.channel,self.channel[1:]+self.channel[:1]):
                if intersects(a,b,c,d):
                    delta=sub(b,a);edge=sub(d,c)
                    cross=lambda u,v:u[0]*v[1]-u[1]*v[0]
                    denominator=cross(delta,edge)
                    if abs(denominator)>1e-12:
                        fraction=cross(sub(c,a),edge)/denominator
                        crossing=tuple(a[i]+fraction*delta[i] for i in (0,1))
                        centre=tuple((access[0][i]+access[1][i])/2 for i in (0,1))
                        if dot(sub(crossing,centre),self.planes[0][1])>1e-7:
                            return None
            if inside(b,self.channel):
                for c,d in zip(self.channel,self.channel[1:]+self.channel[:1]):
                    if all(segment_distance(p,*access)<1e-6 for p in (c,d)):
                        continue
                    if segment_distance(b,c,d)<self.required-1e-7:
                        return None
        events=[]
        for index,(origin,forward,left,low,high,_) in enumerate(self.planes):
            u,v=dot(sub(a,origin),forward),dot(sub(b,origin),forward)
            u=0 if abs(u)<1e-7 else u
            v=0 if abs(v)<1e-7 else v
            if (u<=0<v) or (v<=0<u):
                fraction=-u/(v-u)
                point=(a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1]))
                side=dot(sub(point,origin),left)
                events.append((fraction,index,u<=0<v,low-1e-7<=side<=high+1e-7,point))
        for _,index,forward,opening,point in sorted(events):
            if self.general and self.start_inside_channel and self.initial_progress==1 and index==0:
                continue
            if self.has_entry and progress==0:
                # Approach may cross extended task planes while outside the task.
                # Only a forward crossing of the finite entry window starts it.
                if index==0 and forward and opening:
                    progress=1;channel_start=channel_start or point
                continue
            if self.general:
                # Only finite directed crossings participate in progression.
                # Before the first passage a return approach may cross later ones.
                if progress==0 and index!=0:
                    continue
                if not opening:
                    if index==progress and self.draft['passages'][index-int(bool(self.draft.get('entry')))]['kind']=='turn':
                        return None
                    continue
            if not forward or not opening or index!=progress:
                return None
            progress+=1
        if self.channel and channel_start is not None and not self.channel_contains(channel_start,b):
            return None
        return progress

    def channel_contains(self,a,b):
        if self.reviewed_channel and self.reviewed_channel!=self.channel and not contained(a,b,self.reviewed_channel,self.required):
            return False
        if contained(a,b,self.channel,self.required):
            return True
        if not self.general or self.start_inside_channel or not inside(a,self.channel) or not inside(b,self.channel):
            return False
        access=self.access
        # The selected entrance cap is traversable during the connection. Side
        # boundary clearance and all physical obstacle buffers remain mandatory.
        for c,d in zip(self.channel,self.channel[1:]+self.channel[:1]):
            if all(segment_distance(p,*access)<1e-6 for p in (c,d)):
                continue
            if intersects(a,b,c,d) or min(segment_distance(a,c,d),segment_distance(b,c,d),segment_distance(c,a,b),segment_distance(d,a,b))<self.required-1e-7:
                return False
        return True

    def heuristic(self, point, finish, progress):
        direct=math.dist(point,finish)
        if progress>=len(self.planes):
            return direct
        origin,forward,left,low,high,_=self.planes[progress]
        def distance(p):
            delta=sub(p,origin); lateral=dot(delta,left)
            offset=max(low-lateral,0,lateral-high)
            return math.hypot(dot(delta,forward),offset)
        bound=distance(point)+distance(finish)
        if self.windows:
            a,b=self.windows[-1]
            bound=max(bound,distance(point)+self.remaining_distance[progress]+segment_distance(finish,a,b))
        return max(direct,bound)


def validate_course(object_map,draft):
    course=Course(object_map,draft)
    route=[to_local(draft['start'],course.reference),*[to_local(p,course.reference) for p in draft['waypoints']]]
    draft=course.draft
    errors=[]; progress=course.initial_progress; sections=[]
    preferred=finite(draft.get('preferred_buffer_m',draft['clearance_m']))
    if preferred<course.required:
        errors.append({'reason':'preferred buffer must be at least required buffer','location':None})
    for i,(a,b) in enumerate(zip(route,route[1:])):
        next_progress=course.edge(a,b,progress)
        if next_progress is None:
            errors.append({'reason':f'leg {i} violates course boundary, passage direction, side or order','location':list(a)})
        else:
            progress=next_progress
        achieved=course.clearance(a,b)
        if achieved<preferred:
            sections.append({'leg':i,'clearance_m':achieved})
    if progress!=len(course.planes):
        errors.append({'reason':'route must cross all confirmed passages in order','location':None})
    finish=to_local(draft['finish'],course.reference)
    if any(not contained(finish,finish,p,course.required+draft['finish_radius_m']) for p in [*course.polygons,*([course.channel] if course.channel else [])]):
        errors.append({'reason':'unsafe finish area at course boundary','location':list(finish)})
    if draft.get('planner_task'):
        if draft['planner_task'] not in ('gate','slalom','channel'):
            raise ValueError('unsupported planner task')
        if not draft.get('course_confirmed') or not draft.get('sizes_confirmed') or not draft.get('planning_area') or (not course.general and (not draft.get('entry') or not draft.get('exit'))):
            errors.append({'reason':'incomplete course assignments: confirm sizes, direction, entry, finish and planning area','location':None})
        if draft['planner_task']=='channel' and not draft.get('channel'):
            errors.append({'reason':'channel boundary chains are required','location':None})
        if (draft['planner_task']=='gate' and not any(p['kind']=='gate' for p in draft.get('passages',[]))) or (draft['planner_task']=='slalom' and not any(p['kind']=='turn' for p in draft.get('passages',[]))):
            errors.append({'reason':'incomplete course passage assignments','location':None})
    return errors,sections

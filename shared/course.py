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
    if len(poly)<3 or len(poly)>64 or abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1])))<1e-6:
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
        self.channel=None
        self.has_entry=bool(draft.get("planner_task") and draft.get("entry"))
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
            elif p['kind']=='turn':
                obj=ids[p['buoy']]
                if obj['type']!='cylinder' or p.get('side') not in ('left','right'):
                    raise ValueError('turn requires buoy and passing side')
                origin=to_local(obj['centre'],self.reference)
                offset=obj['radius_m']+self.required
                low,high=(offset,math.inf) if p['side']=='left' else (-math.inf,-offset)
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

    def clearance(self,a,b):
        minimum=min((segment_distance(centre,a,b)-radius for centre,radius in self.circles),default=math.inf)
        for centre,radius,polygon in self.footprints:
            if segment_distance(centre,a,b)-radius<minimum:
                minimum=min(minimum,polygon_gap(polygon,a,b))
        return minimum

    def edge(self,a,b,progress):
        if self.clearance(a,b)<self.required-1e-7 or any(not contained(a,b,p,self.required) for p in self.polygons):
            return None
        entered = not self.has_entry or progress>0
        channel_start = a if entered else None
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
            if self.has_entry and progress==0:
                # Approach may cross extended task planes while outside the task.
                # Only a forward crossing of the finite entry window starts it.
                if index==0 and forward and opening:
                    progress=1;channel_start=point
                continue
            if not forward or not opening or index!=progress:
                return None
            progress+=1
        if self.channel and channel_start is not None and not contained(channel_start,b,self.channel,self.required):
            return None
        return progress

    def heuristic(self, point, finish, progress):
        direct=math.dist(point,finish)
        if progress>=len(self.planes):
            return direct
        origin,forward,left,low,high,_=self.planes[progress]
        def distance(p):
            delta=sub(p,origin); lateral=dot(delta,left)
            offset=max(low-lateral,0,lateral-high)
            return math.hypot(dot(delta,forward),offset)
        return max(direct,distance(point)+distance(finish))


def validate_course(object_map,draft):
    course=Course(object_map,draft)
    route=[to_local(draft['start'],course.reference),*[to_local(p,course.reference) for p in draft['waypoints']]]
    errors=[]; progress=0; sections=[]
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
        if not draft.get('course_confirmed') or not draft.get('sizes_confirmed') or not draft.get('planning_area') or not draft.get('entry') or not draft.get('exit'):
            errors.append({'reason':'incomplete course assignments: confirm sizes, direction, entry, finish and planning area','location':None})
        if draft['planner_task']=='channel' and not draft.get('channel'):
            errors.append({'reason':'channel boundary chains are required','location':None})
        if (draft['planner_task']=='gate' and not any(p['kind']=='gate' for p in draft.get('passages',[]))) or (draft['planner_task']=='slalom' and not any(p['kind']=='turn' for p in draft.get('passages',[]))):
            errors.append({'reason':'incomplete course passage assignments','location':None})
    return errors,sections

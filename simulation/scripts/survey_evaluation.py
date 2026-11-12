"""Build independent physical evaluation requirements from explicit assignments.

Only the evaluator reads physical footprints. Planning receives point surveys.
No labels, nearest-object guesses, or generated passage directions are used.
"""
import math
from shared.geometry import to_local


def unit(delta):
    length = math.hypot(*delta)
    if length < 1e-8:
        raise ValueError('ambiguous evaluation direction')
    return [v/length for v in delta]


def evaluation_course(truth, run, contact_proof=None):
    ref = truth['geographic_reference']
    objects = {o['id']:o for o in [*truth['buoys'], *truth.get('obstacles',[])]}
    position = lambda key: to_local(objects[key]['centre'],ref)
    delta = lambda a,b: [a[i]-b[i] for i in (0,1)]
    c = {'scene_id':truth['scene_id'], 'finite_passages':True,
         'buoys':{k:{'radius_m':o['radius_m']} for k,o in objects.items() if o['type']=='cylinder'},
         'polygon_obstacles':{k:{'pose':[*position(k),0,0,0,o.get('world_yaw_rad',0)], 'footprint':[to_local(p,ref) for p in o['footprint']]} for k,o in objects.items() if o['type']=='polygon'},
         'frozen_objects':{k:position(k) for k in objects}, 'passages':[], 'minimum_clearance_m':.25, 'timeout_s':run['execution_budget_s'],
         'boundary_polygons':[[to_local(p,ref) for p in run['planning_area']]]}
    if contact_proof:
        import hashlib
        c.update(contact_verification_evidence=str(contact_proof.resolve()),contact_verification_sha256=hashlib.sha256(contact_proof.read_bytes()).hexdigest())
    if run.get('planning_mode') in ('run', 'return'):
        return ordered_course(truth, run, c, contact_proof)
    for block in run['blocks']:
        task = block['task'];d = run['task_setup'][task]
        if task == 'channel':
            chains = [[position(key) for key in d['channel_chains'][side]] for side in ('left','right')]
            fractions = []
            for chain in chains:
                dist = [0]
                for a,b in zip(chain,chain[1:]):dist.append(dist[-1]+math.dist(a,b))
                fractions.append([v/dist[-1] for v in dist])
            def at(chain, values, t):
                for i in range(len(chain)-1):
                    if t <= values[i+1]+1e-8:
                        q=(t-values[i])/(values[i+1]-values[i])
                        return [chain[i][j]+q*(chain[i+1][j]-chain[i][j]) for j in (0,1)]
                return chain[-1]
            levels=sorted({round(v,8) for chain in fractions for v in chain})
            pairs=[[at(chain,values,t) for chain,values in zip(chains,fractions)] for t in levels]
            centres=[[sum(v[j] for v in pair)/2 for j in (0,1)] for pair in pairs]
            first=unit(delta(centres[1],centres[0]));last=unit(delta(centres[-1],centres[-2]))
            # Physical boundary and ordered sections retain every chain point.
            c['task_channel'] = chains[0]+list(reversed(chains[1]))
            c['channel_starts_after']=len(c['passages'])
            from shared.course import inside
            block_start = run['start'] if block['waypoint_start'] == 0 else run['waypoints'][block['waypoint_start']-1]
            if not inside(to_local(block_start,ref), c['task_channel']):
                c['channel_entry']={'origin':centres[0][:],'direction':first,'half_width_m':math.dist(*pairs[0])/2}
            pad=run['settings']['clearance_m']+d['finish_radius_m']+1
            centres[0]=[centres[0][i]+pad*first[i] for i in (0,1)]
            centres[-1]=[centres[-1][i]-pad*last[i] for i in (0,1)]
            for i,(pair,origin) in enumerate(zip(pairs,centres)):
                tangent=unit(delta(pair[1],pair[0]));normal=[tangent[1],-tangent[0]]
                hint=first if i==0 else last if i==len(pairs)-1 else delta(centres[i+1],centres[i-1])
                if sum(a*b for a,b in zip(normal,hint))<0:normal=[-v for v in normal]
                half=math.dist(*pair)/2
                c['passages'].append({'id':f'channel:section_{i+1}','block':task,'kind':'gate','origin':origin,'direction':normal,'y_min':-half,'y_max':half})
            continue
        anchors=[]
        for p in d['passages']:
            if p['kind']=='gate':
                a,b=position(p['red']),position(p['green']);anchors.append([(a[i]+b[i])/2 for i in (0,1)])
            else:anchors.append(position(p['buoy']))
        for i,p in enumerate(d['passages']):
            hint=p.get('direction_override') or (d['direction'] if len(anchors)==1 else delta(anchors[min(i+1,len(anchors)-1)],anchors[max(0,i-1)]))
            origin=anchors[i]
            if p['kind']=='gate':
                a,b=position(p['red']),position(p['green']);tangent=unit(delta(b,a));normal=[tangent[1],-tangent[0]]
                if sum(x*y for x,y in zip(normal,hint))<0:normal=[-v for v in normal]
                left=[-normal[1],normal[0]]
                ends=sorted((sum((v[j]-origin[j])*left[j] for j in (0,1)),objects[p[key]]['radius_m']) for v,key in ((a,'red'),(b,'green')))
                passage={'kind':'gate','y_min':ends[0][0]+ends[0][1],'y_max':ends[1][0]-ends[1][1]}
            else:
                normal=unit(hint);left=[-normal[1],normal[0]]
                bounds=[sum((v[j]-origin[j])*left[j] for j in (0,1)) for v in c['boundary_polygons'][0]]
                passage={'kind':'turn','buoy':p['buoy'],'side':p['side'],'y_min':min(bounds),'y_max':max(bounds)}
            c['passages'].append({**passage,'id':task+':'+p['id'],'block':task,'origin':origin,'direction':normal})
    x,y=to_local(run['finish'],ref)
    c['finish']={'x':x,'y':y,'radius_m':1,'speed_m_s':.2,'settle_s':5}
    return c


def ordered_course(truth, run, course, contact_proof=None):
    """Independent requirements retain instance order and each channel lifetime."""
    from copy import deepcopy
    from shared.course import inside
    ref = truth['geographic_reference']
    objects = {o['id']:o for o in [*truth['buoys'], *truth.get('obstacles', [])]}
    pos = lambda key: to_local(objects[key]['centre'], ref)
    course['channels'] = []
    if run['planning_mode'] == 'return':
        for i, water in enumerate(run.get('navigation_water', [])):
            polygon = [to_local(p,ref) for p in water['polygon']]
            if not inside(to_local(run['start'],ref), polygon):
                continue
            a,b = [to_local(p,ref) for p in water['opening']]
            course['channels'].append({'instance_id':f'return-water-{i}', 'polygon':polygon,
                                       'entry':None, 'exit':{'origin':[(a[j]+b[j])/2 for j in (0,1)], 'direction':[-v for v in water['direction']]},
                                       'begin_passage':0,'end_passage':0,'return_escape':True})
    else:
        by_id = {s['id']:s for s in run['steps']}
        for block in run['blocks']:
            step = by_id[block['instance_id']]
            task = step['type']
            if task == 'manual':
                continue
            # Reuse the independent physical-object derivation for one block,
            # then namespace every event by this card's unique instance ID.
            d = deepcopy(step['setup'])
            d['finish_radius_m'] = d.get('finish_radius_m',1)
            one = {**run, 'planning_mode':'legacy', 'task_setup':{task:d}, 'blocks':[{'task':task,'waypoint_start':block['waypoint_start']}]}
            part = evaluation_course(truth,one,contact_proof)
            first = len(course['passages'])
            for p in part['passages']:
                p['id'] = step['id']+':'+p['id'].split(':',1)[-1]
                p['block'] = step['id']
            if task == 'channel':
                left,right = [d['channel_chains'][side] for side in ('left','right')]
                a,b = pos(left[0]),pos(right[0])
                start = [(a[j]+b[j])/2 for j in (0,1)]
                a,b = pos(left[-1]),pos(right[-1])
                end = [(a[j]+b[j])/2 for j in (0,1)]
                # Final physical crossing is the actual last pair, not an inset.
                part['passages'][-1]['origin'] = end
                polygon = [to_local(p,ref) for p in d.get('channel', [])] or [*[pos(k) for k in left],*[pos(k) for k in reversed(right)]]
                course['channels'].append({'instance_id':step['id'],'polygon':polygon,
                                           'entry':{'origin':start,'direction':part['passages'][0]['direction']},
                                           'exit':{'origin':end,'direction':part['passages'][-1]['direction']},
                                           'begin_passage':first,'end_passage':first+len(part['passages'])})
            course['passages'].extend(part['passages'])
    x,y = to_local(run['finish'],ref)
    course['finish'] = {'x':x,'y':y,'radius_m':run['finish_radius_m'],'speed_m_s':.2,'settle_s':5}
    return course

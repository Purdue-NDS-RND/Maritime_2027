import {local,gps} from './buffers.js';

export const TASKS = [
    {id:'gate', title:'Gate', detail:'Pass the entrance gate and stop.'},
    {id:'slalom', title:'Slalom / Dodge', detail:'Weave through the turn buoys and exit gate.'},
    {id:'channel', title:'Channel / Evade', detail:'Cross every channel gate and finish beyond the last pair.'},
    {id:'manual', title:'Manual move', detail:'Queue your own waypoints and stop at the last one.'},
];
export function channelExitFinish(map,draft) {
    if(!map||!draft.channel_chains)return null;
    const objects=new Map(map.buoys.map(o=>[o.id,o]));
    const chains=['left','right'].map(side=>(draft.channel_chains[side]||[]).map(id=>objects.get(id)));
    if(chains.some(chain=>chain.length<2||chain.some(o=>!o)))return null;
    const ref=map.geographic_reference;
    const [a,b]=chains.map(chain=>local(chain.at(-1).centre,ref));
    const previous=chains.map(chain=>local(chain.at(-2).centre,ref));
    const width=Math.hypot(b[0]-a[0],b[1]-a[1]);
    if(width<1e-6)return null;
    const centre=a.map((v,i)=>(v+b[i])/2);
    let forward=[(b[1]-a[1])/width,-(b[0]-a[0])/width];
    if(forward.reduce((sum,v,i)=>sum+v*(centre[i]-(previous[0][i]+previous[1][i])/2),0)<0)forward=forward.map(v=>-v);
    const distance=Math.max(4.5,draft.clearance_m+draft.finish_radius_m+.2);
    const [latitude,longitude]=gps(centre.map((v,i)=>v+distance*forward[i]),ref);
    return {latitude,longitude};
}
export function manualDraft(settings, position) {
    return {task:'custom',waypoints:[],start:position||settings.start,finish:position||settings.start,
        speed_m_s:settings.speed_m_s,clearance_m:settings.clearance_m,...(settings.tower_avoidance?{tower_avoidance:structuredClone(settings.tower_avoidance)}:{}),
        preferred_buffer_m:settings.preferred_buffer_m??settings.clearance_m,
        finish_radius_m:settings.finish_radius_m??1,sizes_confirmed:settings.sizes_confirmed,passages:[]};
}
export const friendly = value => (value||'Unknown object').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
export function configuration(draft) {
    const {planning_notice,waypoints,start,planner_task,course_revision,attempt,derived_sections,excluded_sections,partial_attempt,route_sections,generation_errors,generation_setup_sha256,...roles}=draft;
    return roles;
}
export function heading(direction) {
    if(!direction)return 'Not selected';
    const degrees=(Math.atan2(direction[0],direction[1])*180/Math.PI+360)%360;
    return `${['North','Northeast','East','Southeast','South','Southwest','West','Northwest'][Math.round(degrees/45)%8]} · ${Math.round(degrees)}°`;
}
export function missingSetup(draft) {
    if(!draft.planner_task)return [];
    const missing=[];
    for(const [key,label] of [...(draft.geometry_version===2?[]:[['entry','Task entry'],['exit','Task exit']]),['finish','Finish area'],['direction','Travel direction']])if(!draft[key])missing.push(label);
    if((draft.planning_area||[]).length<3)missing.push('Planning boundary');
    if(draft.planner_task==='channel'&&(draft.channel||[]).length<3&&!(draft.channel_chains?.left?.length>=2&&draft.channel_chains?.right?.length>=2))missing.push('Channel boundary');
    if(draft.planner_task==='gate'&&!draft.passages?.some(p=>p.kind==='gate'))missing.push('Gate pair');
    if(draft.planner_task==='slalom'&&!draft.passages?.some(p=>p.kind==='turn'))missing.push('Slalom turns');
    if(draft.passages?.some(p=>p.kind==='turn'&&!['left','right'].includes(p.side)))missing.push('Passing sides');
    return missing;
}
export function gateWarnings(map,draft) {
    if(!map)return [];
    const objects=new Map(map.buoys.map(o=>[o.id,o]));
    return (draft.passages||[]).filter(p=>p.kind==='gate').flatMap(p=>{
        const a=objects.get(p.red),b=objects.get(p.green);if(!a||!b)return ['Select both gate objects.'];
        const dy=(a.centre.latitude-b.centre.latitude)*111319.49079327357;
        const dx=(a.centre.longitude-b.centre.longitude)*111319.49079327357*Math.cos((a.centre.latitude+b.centre.latitude)*Math.PI/360);
        const opening=Math.hypot(dx,dy)-(a.radius_m??0)-(b.radius_m??0);
        const hard=obj=>obj.object_type==='detector'?(draft.tower_avoidance?.overrides?.[obj.id]?.hard_m??draft.tower_avoidance?.hard_m??draft.clearance_m):draft.clearance_m;
        const needed=hard(a)+hard(b);
        return opening+1e-6<needed?[`Gate opening: ${opening.toFixed(2)} m. Your hard buffers need ${needed.toFixed(2)} m. Review the buffer allowance or the opening before generating.`]:[];
    });
}

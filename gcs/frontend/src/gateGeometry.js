// Assignment changes are explicit inputs and always revoke generated authority.
export function replaceGateObject(draft, [instanceId, passageId, endpoint], object) {
    const card=draft.steps.find(s=>s.id===instanceId);
    const passage=card?.setup.passages?.find(p=>p.id===passageId);
    if(!passage||passage.kind!=='gate'||!['red','green'].includes(endpoint))throw new Error('Select a gate endpoint again.');
    if(!['point','cylinder'].includes(object.type)||object.object_type==='detector')throw new Error('Choose a buoy point, not a tower or polygon.');
    if(object.id===passage[endpoint==='red'?'green':'red'])throw new Error('A gate needs two different buoys. Choose another buoy.');
    const setup={...card.setup,course_confirmed:false,derived_sections:[],passages:card.setup.passages.map(p=>p.id===passageId?{...p,[endpoint]:object.id}:p)};
    return {...draft,steps:draft.steps.map(s=>s.id===instanceId?{...s,setup}:s),shared_crossings:[],waypoints:[],generation_identity:null};
}

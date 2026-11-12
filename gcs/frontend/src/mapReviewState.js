export const isPoint = object => ['point','cylinder'].includes(object.type);
export const isNavigation = object => isPoint(object) && object.object_type==='buoy' && ['red','green'].includes(object.category);
export const untypedNavigation = objects => objects.filter(o=>isPoint(o) && (!o.object_type || o.object_type==='unknown') && ['red','green'].includes(o.category));
export const sameRoles = (first,second) => !!first && !!second && Object.keys(first).length===Object.keys(second).length && Object.entries(first).every(([role,id])=>second[role]===id);
export const roleName = role => role.replace('slalom.entrance.','Starting gate · ').replace('slalom.exit.','Exit · ').replace('slalom.turn.','Turn ').replace('channel.','Boundary · ').replaceAll('.',' ');

export const isUnknownObject = object => !object.object_type || object.object_type==='unknown';
export const displayColour = (object,knownColour) => isUnknownObject(object)?'#999':knownColour;

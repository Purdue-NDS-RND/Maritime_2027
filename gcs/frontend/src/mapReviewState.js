export const isPoint = object => ['point','cylinder'].includes(object.type);
export const isNavigation = object => isPoint(object) && object.object_type==='buoy' && ['red','green'].includes(object.category);
export const untypedNavigation = objects => objects.filter(o=>isPoint(o) && (!o.object_type || o.object_type==='unknown') && ['red','green'].includes(o.category));
export const sameRoles = (first,second) => !!first && !!second && Object.keys(first).length===Object.keys(second).length && Object.entries(first).every(([role,id])=>second[role]===id);
export const roleName = role => role.replace('slalom.entrance.','Starting gate · ').replace('slalom.exit.','Exit · ').replace('slalom.turn.','Turn ').replace('channel.','Boundary · ').replaceAll('.',' ');

export const isUnknownObject = object => !object.object_type || object.object_type==='unknown';
export const displayColour = (object,knownColour) => isUnknownObject(object)?'#999':knownColour;

export const BUOY_COLOURS = ['red','green','purple','blue','orange','yellow','white','black','zebra','brown','cyan'];
export const canQuickEdit = object => isPoint(object) && (!object.object_type || ['unknown','buoy'].includes(object.object_type));
export function moveMapObject(map,id,centre) {
    return {...map,...Object.fromEntries(['buoys','obstacles'].map(key=>[key,(map[key]||[]).map(object=>{
        if(object.id!==id)return object;
        const moved={...object,centre};
        if(object.footprint){
            const dy=centre.latitude-object.centre.latitude,dx=centre.longitude-object.centre.longitude;
            moved.footprint=object.footprint.map(p=>({...p,latitude:p.latitude+dy,longitude:p.longitude+dx}));
        }
        return moved;
    })]))};
}
export function labelMapBuoy(map,id,category) {
    return {...map,...Object.fromEntries(['buoys','obstacles'].map(key=>[key,(map[key]||[]).map(object=>object.id===id&&canQuickEdit(object)?{...object,category,object_type:'buoy'}:object)]))};
}

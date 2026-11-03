import {missingSetup,gateWarnings} from './workflow.js';
import {settingsError} from './settings.js';

export function freshStatus(status,ageMs) {
    return !!status?.position&&!status.connection_lost&&ageMs<=3500&&
        ['position_age_s','heartbeat_age_s'].every(key=>Number.isFinite(status[key])&&status[key]>=0&&status[key]<=3);
}
export function generationChecks(map,draft,stale) {
    const missing=missingSetup(draft),warnings=gateWarnings(map,draft),attempt=draft.attempt||{};
    const partial=attempt.mode==='remaining';
    return [
        {id:'sizes',label:'Object map reviewed',ready:!!draft.sizes_confirmed,detail:'Review object positions and types before planning.',step:1},
        {id:'assignments',label:'Assignments & boundaries',ready:!missing.length,detail:missing.length?`Still needed: ${missing.join(', ')}.`:'Required task assignments are present.',section:'assignments'},
        {id:'geometry',label:'Geometry reviewed',ready:draft.geometry_version!==2||!!draft.derived_sections?.length,detail:'Use Review geometry on map to check numbered passages and arrows.',action:'geometry'},
        {id:'confirmed',label:'Task setup confirmed',ready:!!draft.course_confirmed,detail:'Confirm the reviewed task setup below.',action:'confirm'},
        {id:'opening',label:'Required clearance fits',ready:!warnings.length,detail:warnings.join(' '),step:2},
        {id:'start',label:attempt.start_source==='manual'?'Manual start selected':'Fresh live start',ready:attempt.start_source==='manual'||!stale,detail:'Live position or heartbeat is unavailable or over 3 seconds old. Reconnect the boat, or explicitly select Manual start for offline planning.',action:'start'},
        {id:'remaining',label:'Partial selection confirmed',ready:!partial||(Number.isInteger(attempt.first_section)&&attempt.selection_confirmed),detail:'Choose and confirm the first included section; earlier sections will be excluded.',action:'remaining'},
        {id:'settings',label:'Valid planning settings',ready:!settingsError({version:1,...draft,tower_avoidance:draft.tower_avoidance||{hard_m:draft.clearance_m,soft_m:draft.preferred_buffer_m??draft.clearance_m,strength:10,overrides:{}},task_overrides:{}}),detail:'Check speed, clearance and tower distances in Configure.',step:2},
    ].filter(check=>check.id!=='remaining'||partial);
}
export function reviewBlocks({draft,routeVisible,dirty,validation,approved,uploaded,stale,status,busy,pending,mission}) {
    const route=!routeVisible?'Generate a fresh route in Task setup first.':!draft.waypoints?.length?'Add at least one waypoint before validation.':'';
    const currentMission=approved&&mission&&status?.mission_id===mission;
    const execution=currentMission&&['starting','executing','stopping'].includes(status?.state)?'This mission is already starting, running or stopping. Monitor it or use Hold / Stop.':currentMission&&status?.state==='complete'?'This mission has finished. Generate and review a fresh attempt to run it again.':'';
    const working=busy?'Wait for the current request to finish.':'';
    return {
        validate:working||route,
        approve:working||route||(dirty?'Save and validate the edited route first.':!validation?.valid?'Validate the route and resolve its errors first.':approved?'This route is already approved.':''),
        upload:working||route||(!approved?'Validate and approve this route first.':stale?'Reconnect the boat and wait for fresh position and heartbeat.':status?.armed?'Disarm using Boat controls above before uploading. Go / Start arms automatically.':status?.mode===10?'Select Hold / Stop in Boat controls before uploading.':pending?.command==='upload'?'Upload is awaiting the boat’s acknowledgement and readback.':''),
        start:working||route||(!approved?'Validate and approve this route first.':stale?'Reconnect the boat and wait for fresh position and heartbeat.':pending?.command==='start'?'Start request is awaiting confirmation.':execution||(!uploaded?'Upload this approved route and wait for confirmation.':'')),
    };
}
export function errorText(detail) {
    if(typeof detail==='string')return detail;
    if(Array.isArray(detail))return detail.map(item=>item.reason||[item.loc?.join(' → '),item.msg].filter(Boolean).join(': ')).join('; ');
    if(detail?.errors)return detail.errors.map(item=>item.reason).join('; ');
    return detail?.message||detail?.reason||detail?.text||'The request could not be completed. Check the connection and try again.';
}
export function explainFailure(error) {
    const text=errorText(error?.detail??error?.message??error);
    let title='Action needs attention',next='Review the message below and correct the highlighted setup before trying again.',step=3;
    if(/time limit|search exhaust|bounded|search budget/i.test(text)){title='No route found within the search budget';next='This does not prove the course is blocked. Check the approach, boundaries and assignments before trying again.';}
    else if(/insufficient gate|opening.*blocked|entry window.*blocked/i.test(text)){title='Opening blocked at required clearance';next='Review the assigned objects and clearance in Configure. Hard clearance has not been reduced.';step=2;}
    else if(/unsafe.*start|unsafe planning start|actual position|task progress|start connection/i.test(text)){title='Starting position needs review';next='Inspect the marked start conflict. Correct the start or task setup, then generate and review a fresh attempt.';}
    else if(/unsafe finish|finish area|finish.*clearance/i.test(text)){title='Finish area needs more room';next='Move the finish to clear water, including space for its stopping radius, then regenerate.';}
    else if(/age|heartbeat|fresh|stale/i.test(text)){title='Fresh boat position required';next='Reconnect the boat, or explicitly select Manual start in Task setup for offline planning.';}
    else if(/soft.*hard|preferred.*required|settings|nonnegative|positive speed/i.test(text)){title='Check the course settings';next='Correct the speed or distance values in Configure.';step=2;}
    else if(/fetch|network|connection|offline|unknown.*outcome|outcome unknown|aborted|HTTP 5[0-9][0-9]/i.test(text)){title='Connection interrupted';next='Check boat status and Command results before retrying Upload or Start; the previous outcome may be unknown.';}
    return {title,text,next,step};
}
export function operationNotice(operation) {
    const command={upload:'Upload',start:'Start',stop:'Hold / Stop',disarm:'Disarm'}[operation.command]||'Request';
    if(['failed','unknown','cancelled'].includes(operation.state))return {
        kind:'error',title:`${command} ${operation.state==='unknown'?'outcome unknown':operation.state}`,
        text:operation.detail||`${command} was not confirmed.`,detail:operation.detail||`${command} was not confirmed.`,
        next:'Inspect Command results and the actual vehicle state before retrying. A request receipt alone does not confirm execution.',step:4,reviewLabel:'Review command results',
    };
    if(operation.state==='succeeded')return {kind:'info',text:`${command} confirmed.${operation.command==='upload'?' Mission upload and readback succeeded. Start remains a separate action.':''}`};
    return null;
}

import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Planner,{WorkflowNav} from '../src/Planner.jsx';
import BoatControls from '../src/BoatControls.jsx';
import {moveStep,duplicateStep} from '../src/RunBuilder.jsx';
import {defaultSettings} from '../src/settings.js';
import {courseOverlay} from '../src/courseOverlay.js';
import {addedObject,editObjects,removeObject,AssignmentReview} from '../src/MapReview.jsx';
import {suggestBoundary} from '../src/planningBoundary.js';
const map=JSON.parse(fs.readFileSync('../examples/competition-gps-map.json'));
const draft={planning_mode:'run',steps:[],settings:defaultSettings(),waypoints:[],start:map.geographic_reference,planning_area:suggestBoundary(map),sizes_confirmed:true,attempt:{mode:'full',start_source:'live'},execution_budget_s:300};
const props={workspace:{map,run_draft:draft,game_settings:defaultSettings()},draft,mode:'inspect',selected:'',operations:[],results:{},stale:true,routeVisible:false};
for(const step of [1,2,3,4]){
 const html=renderToStaticMarkup(<Planner {...props} step={step}/>);
 const nav=renderToStaticMarkup(<WorkflowNav {...props} step={step}/>);
 assert.match(nav,/Map/);assert.match(nav,/Configure/);assert.match(nav,/Build run/);assert.match(nav,/Review &amp; execute/);
 assert.doesNotMatch(html,/Planning mode|Single task|Competition run|Saved queue|Optional task overrides/);
 if(step===1){assert.match(html,/Load full competition map/);assert.match(html,/I reviewed the map — continue/);assert.match(html,/Map preparation/);assert.doesNotMatch(html,/Selected task templates|expanded_states/);assert.match(html,/Boundary extra room/);assert.match(html,/Regenerate/);assert.match(html,/Edit corners/);assert.doesNotMatch(html,/disabled=""[^>]*>I reviewed the map — continue/);}
 if(step===2){assert.match(html,/Hard exclusion/);assert.match(html,/Start, boundary/);assert.match(html,/Continue to Build run/);}
 if(step===3){assert.match(html,/Your run is empty/);for(const name of ['Gate','Slalom','Channel','Manual'])assert.match(html,new RegExp('＋ '+name));assert.doesNotMatch(html,/Task type|Hard exclusion/);assert.match(html,/disabled=""[^>]*>Generate run/);}
 if(step===4){assert.match(html,/disabled=""[^>]*>1. Validate route/);}
}
const cards=[{id:'one',type:'manual',setup:{waypoints:[map.geographic_reference],course_confirmed:true}},{id:'two',type:'gate',setup:{passages:[],geometry_version:2}}];
const manual=renderToStaticMarkup(<Planner {...props} step={3} selectedCard="one" draft={{...draft,steps:cards}}/>);
assert.match(manual,/Draw manual waypoints/);assert.match(manual,/Duplicate/);assert.match(manual,/Move Manual 1 up/);assert.match(manual,/Move Manual 1 down/);assert.match(manual,/draggable="true"/);
const copied=duplicateStep(cards[0],'copy');copied.setup.waypoints[0].latitude=1;assert.notEqual(copied.setup.waypoints[0].latitude,cards[0].setup.waypoints[0].latitude);assert.equal(copied.id,'copy');
assert.deepEqual(moveStep(cards,0,1).map(s=>s.id),['two','one']);
const returns=renderToStaticMarkup(<Planner {...props} step={4} draft={{...draft,planning_mode:'return',return_target:draft.start}}/>);
assert.match(returns,/1 m stopping area/);assert.match(returns,/Explicitly Disarm/);
const controls=target=>renderToStaticMarkup(<BoatControls status={{armed:false,mode:4,speed_m_s:0}} stale={false} returnTarget={target}/>);
assert.match(controls(null),/disabled=""[^>]*>Return now/);assert.doesNotMatch(controls(draft.start),/disabled=""[^>]*>Return now/);
const source=fs.readFileSync('src/main.jsx','utf8');assert.doesNotMatch(source,/localStorage|sessionStorage/);
console.log('Four-view planning workspace, independent cards, return review and controls render.');

const gateDraft={...draft,steps:[{id:'gate',type:'gate',setup:{geometry_version:2,passages:[{id:'passage',kind:'gate',red:'a',green:'b'}]}}]};
const gateHtml=renderToStaticMarkup(<Planner {...props} step={3} selectedCard="gate" draft={gateDraft}/>);
assert.match(gateHtml,/Gate 1 · show pair on map/);assert.match(gateHtml,/Replace first buoy/);assert.match(gateHtml,/Replace second buoy/);

const roles={slalom:{'slalom.entrance.red':'dodge_gate_a_red','slalom.entrance.green':'dodge_gate_a_green','slalom.turn.1':'dodge_turn_1','slalom.turn.2':'dodge_turn_2','slalom.turn.3':'dodge_turn_3','slalom.turn.4':'dodge_turn_4','slalom.exit.red':'dodge_gate_b_red','slalom.exit.green':'dodge_gate_b_green'},channel:Object.fromEntries(['red','green'].flatMap((c)=>[1,2,3].map(i=>[`channel.${c}.${i}`,`evade_${c==='red'?'left':'right'}_${i-1}`])))};
for(const tasks of [roles,{gate:Object.fromEntries(Object.entries(roles.slalom).slice(0,2))}]){
 const geometry=courseOverlay(map,tasks);assert.ok(geometry.lines.some(l=>l.kind==='arrow'));
 for(const p of [...geometry.lines.flatMap(l=>l.points),...geometry.labels.map(l=>l.position)])assert.ok(p.length===2&&p.every(Number.isFinite));
}
const proposal={id:'candidate',tasks:roles,score:1,unresolved:['gate'],details:Object.fromEntries(Object.keys(roles).map(t=>[t,{score_components:{distance:1,heading:0},measurements:[{label:'Spacing',actual_m:12,nominal_m:9,normalized_residual:1.1,unusual:true}]}]))};
const compilerHtml=renderToStaticMarkup(<Planner {...props} step={1} workspace={{...props.workspace,compilation:{candidates:[proposal],expanded_states:25,elapsed_s:.1,search_exhausted:true,limits:['state_limit'],partials:{slalom:{}}},course_assignments:{slalom:{roles:roles.slalom,status:'review_required'}}}}/>);
for(const text of ['Review tasks','Confirm Slalom','Search truncated','Unusual:','Download course JSON','Continue to Configure']){
 assert.ok(compilerHtml.includes(text),text);
}
assert.doesNotMatch(compilerHtml,/Selected task templates|Preview ranked alternative/);
assert.match(compilerHtml,/Option 1/);assert.match(compilerHtml,/Measurements &amp; search details/);
const changed=editObjects(map,['dodge_turn_1'],{object_type:'unknown'});assert.equal(map.buoys.find(o=>o.id==='dodge_turn_1').object_type,'buoy');assert.equal(changed.buoys.find(o=>o.id==='dodge_turn_1').object_type,'unknown');
assert.ok(!removeObject(map,'dodge_turn_1').buoys.some(o=>o.id==='dodge_turn_1'));
assert.deepEqual(addedObject(map.geographic_reference,'opaque').centre,map.geographic_reference);

const unknownMap={...map,buoys:map.buoys.map(o=>({...o,object_type:'unknown'}))};
const cleanupHtml=renderToStaticMarkup(<Planner {...props} step={1} workspace={{...props.workspace,map:unknownMap}}/>);
assert.match(cleanupHtml,/Mark 14 red\/green detections as buoys/);
assert.match(cleanupHtml,/disabled=""[^>]*>I reviewed the map — continue/);
assert.doesNotMatch(cleanupHtml,/Compile course →|Confirm Slalom|search details/);
const missingBoundaryHtml=renderToStaticMarkup(<Planner {...props} step={1} draft={{...draft,planning_area:[]}}/>);
assert.match(missingBoundaryHtml,/disabled=""[^>]*>I reviewed the map — continue/);
assert.match(missingBoundaryHtml,/disabled=""[^>]*>Map checked — assign tasks manually/);
const invalidBoundaryConfiguration=renderToStaticMarkup(<Planner {...props} step={2} draft={{...draft,planning_area:[]}}/>);
assert.match(invalidBoundaryConfiguration,/disabled=""[^>]*>Continue to Build run/);
const confirmedHtml=renderToStaticMarkup(<AssignmentReview candidate={proposal} assignments={{slalom:{roles:roles.slalom,status:'accepted'}}}/>);
assert.match(confirmedHtml,/disabled=""[^>]*>Slalom confirmed/);
const differentHtml=renderToStaticMarkup(<AssignmentReview candidate={proposal} assignments={{slalom:{roles:{...roles.slalom,'slalom.turn.1':'different'},status:'accepted'}}}/>);
assert.match(differentHtml,/>Confirm Slalom</);assert.doesNotMatch(differentHtml,/>Slalom confirmed</);

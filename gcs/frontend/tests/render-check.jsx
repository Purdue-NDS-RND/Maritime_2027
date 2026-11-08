import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Planner,{WorkflowNav} from '../src/Planner.jsx';
import BoatControls from '../src/BoatControls.jsx';
import {moveStep,duplicateStep} from '../src/RunBuilder.jsx';
import {defaultSettings} from '../src/settings.js';
const map=JSON.parse(fs.readFileSync('../examples/competition-gps-map.json'));
const draft={planning_mode:'run',steps:[],settings:defaultSettings(),waypoints:[],start:map.geographic_reference,planning_area:[],sizes_confirmed:true,attempt:{mode:'full',start_source:'live'},execution_budget_s:300};
const props={workspace:{map,run_draft:draft,game_settings:defaultSettings()},draft,mode:'inspect',selected:'',operations:[],results:{},stale:true,routeVisible:false};
for(const step of [1,2,3,4]){
 const html=renderToStaticMarkup(<Planner {...props} step={step}/>);
 const nav=renderToStaticMarkup(<WorkflowNav {...props} step={step}/>);
 assert.match(nav,/Map/);assert.match(nav,/Configure/);assert.match(nav,/Build run/);assert.match(nav,/Review &amp; execute/);
 assert.doesNotMatch(html,/Planning mode|Single task|Competition run|Saved queue|Optional task overrides/);
 if(step===1){assert.match(html,/Load full competition map/);assert.match(html,/I reviewed object positions and types/);}
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

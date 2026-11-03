import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Planner from '../src/Planner.jsx';
import BoatControls from '../src/BoatControls.jsx';
const map=JSON.parse(fs.readFileSync('../examples/competition-gps-map.json'));
const draft={waypoints:[],start:map.geographic_reference,finish:map.geographic_reference,speed_m_s:.5,clearance_m:1.8,passages:[],sizes_confirmed:true};
const props={workspace:{map,draft,tasks:{}},draft,mode:'inspect',step:1,selected:'',operations:[],results:{},stale:true};
for(const step of [1,2,3]){
 const html=renderToStaticMarkup(<Planner {...props} step={step}/>);
 assert.match(html,/Planning steps/);
 if(step===1){assert.match(html,/Load full competition map/);assert.doesNotMatch(html,/Generate route|Upload to boat|Course passage order/);}
 if(step===2){assert.match(html,/Slalom \/ Dodge/);assert.match(html,/Channel \/ Evade/);assert.doesNotMatch(html,/Upload to boat/);}
 if(step===3){assert.match(html,/Validate route/);assert.match(html,/Boat offline/);assert.match(html,/Upload to boat/);}
}
console.log('All three workflow panels render; offline command controls remain gated.');
const manual={...draft,task:'custom'};
const setup=renderToStaticMarkup(<Planner {...props} draft={manual} step={2}/>);
assert.match(setup,/Manual move/);assert.match(setup,/Draw waypoints/);
assert.doesNotMatch(setup,/Generate route/);
const review=renderToStaticMarkup(<Planner {...props} draft={manual} step={3}/>);
assert.match(review,/Review manual move/);assert.match(review,/4. Go/);
const controls=(status,stale=false)=>renderToStaticMarkup(<BoatControls status={status} stale={stale}/>);
const settled=controls({armed:true,mode:4,speed_m_s:0,gps_fix:6});
assert.match(settled,/Ready to Disarm/);assert.match(settled,/>Disarm<\/button>/);
assert.doesNotMatch(settled,/disabled=""[^>]*>Disarm<\/button>/);
for(const status of [{armed:true,mode:10,speed_m_s:0},{armed:true,mode:4,speed_m_s:1},{armed:true,mode:4,speed_m_s:null}]){
 assert.match(controls(status),/disabled=""[^>]*>Disarm<\/button>/);
}
assert.match(controls({armed:false,mode:4,speed_m_s:0}),/Disarmed ✓/);
assert.match(controls({armed:true,mode:4,speed_m_s:0},true),/Status unavailable/);
assert.match(controls({armed:true,mode:4,speed_m_s:0},true),/disabled=""[^>]*>Disarm<\/button>/);
const armedReview=renderToStaticMarkup(<Planner {...props} draft={manual} step={3} stale={false} dirty={false} workspace={{...props.workspace,approval:{envelope:{mission:{mission_id:'test'}}}}} status={{armed:true,mode:4}}/>);
assert.match(armedReview,/disabled=""[^>]*>3. Upload to boat<\/button>/);
assert.match(armedReview,/Disarm using Boat controls/);
const general={...draft,planner_task:'channel',geometry_version:2,attempt:{mode:'remaining',start_source:'live',first_section:1},derived_sections:[{id:'section_1'},{id:'section_2'}]};
const generalHtml=renderToStaticMarkup(<Planner {...props} draft={general} step={2}/>);
assert.match(generalHtml,/Live boat/);assert.match(generalHtml,/Full task/);assert.match(generalHtml,/Remaining section/);
assert.match(generalHtml,/no completion credit/);assert.match(generalHtml,/I confirm this partial selection/);
assert.match(generalHtml,/disabled=""[^>]*>Generate route/);
assert.doesNotMatch(generalHtml,/Entry is a separate/);

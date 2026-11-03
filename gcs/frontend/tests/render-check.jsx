import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Planner from '../src/Planner.jsx';
import BoatControls from '../src/BoatControls.jsx';
import Feedback,{DiagnosticList,Readiness} from '../src/Feedback.jsx';
const map=JSON.parse(fs.readFileSync('../examples/competition-gps-map.json'));
const draft={waypoints:[],start:map.geographic_reference,finish:map.geographic_reference,speed_m_s:.5,clearance_m:1.8,passages:[],sizes_confirmed:true};
const props={workspace:{map,draft,tasks:{}},draft,mode:'inspect',step:1,selected:'',operations:[],results:{},stale:true};
for(const step of [1,2,3,4]){
 const html=renderToStaticMarkup(<Planner {...props} step={step}/>);
 assert.match(html,/Planning steps/);
 if(step===1){assert.match(html,/Load full competition map/);assert.doesNotMatch(html,/Generate route|Upload to boat|Course passage order/);}
 if(step===2){assert.match(html,/Configure the course/);assert.match(html,/Hard exclusion/);assert.match(html,/Soft avoidance/);assert.doesNotMatch(html,/Upload to boat/);}
 if(step===3){assert.match(html,/Slalom \/ Dodge/);assert.match(html,/Channel \/ Evade/);assert.doesNotMatch(html,/Upload to boat/);}
 if(step===4){assert.match(html,/Validate route/);assert.match(html,/Boat offline/);assert.match(html,/Upload to boat/);}
}
console.log('All four workflow panels render; offline command controls remain gated.');
const manual={...draft,task:'custom'};
const setup=renderToStaticMarkup(<Planner {...props} draft={manual} step={3}/>);
assert.match(setup,/Manual move/);assert.match(setup,/Draw waypoints/);
assert.doesNotMatch(setup,/Generate route/);
const review=renderToStaticMarkup(<Planner {...props} draft={manual} step={4}/>);
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
const armedReview=renderToStaticMarkup(<Planner {...props} draft={{...manual,waypoints:[map.geographic_reference]}} step={4} stale={false} dirty={false} workspace={{...props.workspace,approval:{envelope:{mission:{mission_id:'test'}}}}} status={{armed:true,mode:4}}/>);
assert.match(armedReview,/disabled=""[^>]*>3. Upload to boat<\/button>/);
assert.match(armedReview,/Disarm using Boat controls/);
const general={...draft,planner_task:'channel',geometry_version:2,attempt:{mode:'remaining',start_source:'live',first_section:1},derived_sections:[{id:'section_1'},{id:'section_2'}]};
const generalHtml=renderToStaticMarkup(<Planner {...props} draft={general} step={3}/>);
assert.match(generalHtml,/Live boat/);assert.match(generalHtml,/Full task/);assert.match(generalHtml,/Remaining section/);
assert.match(generalHtml,/no completion credit/);assert.match(generalHtml,/I confirm this partial selection/);
assert.match(generalHtml,/disabled=""[^>]*>Generate route/);
assert.doesNotMatch(generalHtml,/Entry is a separate/);

const hidden=renderToStaticMarkup(<Planner {...props} step={4} routeVisible={false} draft={{...general,waypoints:[map.geographic_reference]}}/>);
assert.match(hidden,/Generate this task/);
assert.match(hidden,/disabled=""[^>]*>1. Validate route/);
const tower=map.obstacles.find(o=>o.object_type==='detector');
assert.ok(tower,'Full competition map must have a tower');
const settingsHtml=renderToStaticMarkup(<Planner {...props} step={2} selected={tower.id}/>);
assert.match(settingsHtml,/Use individual distances/);

const blocked=renderToStaticMarkup(<Planner {...props} step={3} draft={{...general,attempt:{start_source:'live',mode:'full'}}}/>);
assert.match(blocked,/Generation readiness/);assert.match(blocked,/Fresh live start/);
assert.match(blocked,/Choose start source/);assert.match(blocked,/Review geometry/);
const failure=renderToStaticMarkup(<Feedback notice={{kind:'error',detail:'unsafe planning start: tower',errors:[{reason:'unsafe planning start',location:[1,2]}]}}/>);
assert.match(failure,/Starting position needs review/);assert.match(failure,/Locate on map/);
const waiting=renderToStaticMarkup(<Feedback busy label="Generating route" elapsed={14}/>);
assert.match(waiting,/14s elapsed/);assert.match(waiting,/60-second limit/);
const located=renderToStaticMarkup(<DiagnosticList errors={[{reason:'unsafe finish area',location:[0,1]}]}/>);
assert.match(located,/Finish area needs more room/);assert.match(located,/Locate on map/);

const failedSetup=renderToStaticMarkup(<Readiness checks={[{id:'ready',ready:true}]} failed/>);
assert.match(failedSetup,/Last generation failed/);assert.doesNotMatch(failedSetup,/readiness ready/);
const asyncFailure=renderToStaticMarkup(<Feedback notice={{kind:'error',title:'Upload failed',detail:'readback mismatch',next:'Inspect the command result',step:4,reviewLabel:'Review command results'}}/>);
assert.match(asyncFailure,/Upload failed/);assert.match(asyncFailure,/Review command results/);

// Browser-local command IDs survive reload before their async results arrive.
// Missing results and an absent approval must never be treated as a match.
const restoredHistory=renderToStaticMarkup(<Planner {...props} operations={['old-stop','old-disarm']} results={{}} routeVisible={false} taskSelected={false}/>);
assert.match(restoredHistory,/Check your object map/);
const pendingHistory=renderToStaticMarkup(<Planner {...props} step={4} operations={['upload']} results={{upload:{command:'upload',mission_id:'approved',state:'pending'}}} draft={{...manual,waypoints:[map.geographic_reference]}} workspace={{...props.workspace,approval:{envelope:{mission:{mission_id:'approved'}}}}} stale={false} dirty={false} status={{armed:false,mode:4}}/>);
assert.match(pendingHistory,/awaiting the boat’s acknowledgement and readback/);

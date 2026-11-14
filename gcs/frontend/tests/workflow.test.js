import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {heading,missingSetup,gateWarnings,configuration,channelExitFinish} from '../src/workflow.js';
import {local} from '../src/buffers.js';
const map=JSON.parse(fs.readFileSync(new URL('../../examples/competition-gps-map.json',import.meta.url)));
test('channel finish suggestion is beyond the last actual pair, with settings retained',()=>{
 const d={clearance_m:2,finish_radius_m:1,channel_chains:{left:['evade_left_0','evade_left_1','evade_left_2'],right:['evade_right_0','evade_right_1','evade_right_2']}};
 const finish=local(channelExitFinish(map,d),map.geographic_reference);
 const pair=['evade_left_2','evade_right_2'].map(id=>local(map.buoys.find(o=>o.id===id).centre,map.geographic_reference));
 assert.ok(Math.abs(finish[1]-(pair[0][1]+pair[1][1])/2+4.5)<1e-6);
 assert.equal(d.clearance_m,2);
 assert.equal(channelExitFinish(map,{...d,channel_chains:{}}),null);
});
test('competition directions have useful labels',()=>{assert.equal(heading([-1,0]),'West · 270°');assert.equal(heading([0,-1]),'South · 180°');});
test('setup checklist explains what is absent',()=>{assert.deepEqual(missingSetup({planner_task:'channel',finish:{}}),['Task entry','Task exit','Travel direction','Planning boundary','Channel boundary']);});
test('slalom rejects a legacy starting gate and accepts turns followed by the exit',()=>{
 const draft={planner_task:'slalom',geometry_version:2,finish:{},direction:[1,0],planning_area:[{},{},{}],passages:[{kind:'turn',side:'left'},{kind:'gate'}]};
 assert.deepEqual(missingSetup(draft),[]);
 assert.deepEqual(missingSetup({...draft,passages:[{kind:'gate'},...draft.passages]}),['Move the starting gate to a separate Gate task']);
});
test('gate opening warning explains blocked opening and clears for feasible setting',()=>{
 const d={passages:[{kind:'gate',red:'dodge_gate_a_red',green:'dodge_gate_a_green'}],clearance_m:2.1};
 assert.match(gateWarnings(map,d)[0],/4.00 m.*4.20 m/);
 assert.deepEqual(gateWarnings(map,{...d,clearance_m:1.5}),[]);
});
test('course roles never capture route waypoints or planning start',()=>{
 assert.deepEqual(configuration({start:{},waypoints:[{}],planner_task:'gate',course_revision:'old',direction:[-1,0]}),{direction:[-1,0]});
});
test('manual move starts a clean route without inherited task geometry',async()=>{
 const {manualDraft}=await import('../src/workflow.js');
 const position={latitude:40,longitude:-86};
 const d=manualDraft({planner_task:'channel',channel:[{}],entry:{},waypoints:[{}],speed_m_s:2,clearance_m:2,finish_radius_m:1,sizes_confirmed:true},position);
 assert.deepEqual(d.start,position);assert.deepEqual(d.waypoints,[]);
 assert.equal(d.planner_task,undefined);assert.equal(d.channel,undefined);
 assert.equal(d.speed_m_s,2);assert.equal(d.clearance_m,2);
});
test('version 2 has automatic approach and separates attempts from task setup',()=>{
 const d={geometry_version:2,planner_task:'channel',finish:{},direction:[1,0],planning_area:[{},{},{}],channel:[{},{},{}],attempt:{mode:'remaining'},route_sections:[{}],derived_sections:[{}]};
 assert.deepEqual(missingSetup(d),[]);
 const config=configuration(d);
 assert.equal(config.attempt,undefined);assert.equal(config.route_sections,undefined);assert.equal(config.derived_sections,undefined);
});

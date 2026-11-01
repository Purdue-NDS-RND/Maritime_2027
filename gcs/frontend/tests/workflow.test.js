import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {heading,missingSetup,gateWarnings,configuration} from '../src/workflow.js';
const map=JSON.parse(fs.readFileSync(new URL('../../examples/competition-gps-map.json',import.meta.url)));
test('competition directions have useful labels',()=>{assert.equal(heading([-1,0]),'West · 270°');assert.equal(heading([0,-1]),'South · 180°');});
test('setup checklist explains what is absent',()=>{assert.deepEqual(missingSetup({planner_task:'channel',finish:{}}),['Task entry','Task exit','Travel direction','Planning boundary','Channel boundary']);});
test('gate opening warning explains default failure and clears for feasible setting',()=>{
 const d={passages:[{kind:'gate',red:'dodge_gate_a_red',green:'dodge_gate_a_green'}],clearance_m:1.8};
 assert.match(gateWarnings(map,d)[0],/3.52 m.*3.60 m/);
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

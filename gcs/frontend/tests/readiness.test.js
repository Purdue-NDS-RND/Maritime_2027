import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {freshStatus,generationChecks,reviewBlocks,errorText,explainFailure,operationNotice} from '../src/readiness.js';
import {defaultSettings,settingsError} from '../src/settings.js';
const map=JSON.parse(fs.readFileSync(new URL('../../examples/competition-gps-map.json',import.meta.url)));
const draft={...defaultSettings({clearance_m:1.5}),geometry_version:2,planner_task:'gate',waypoints:[{}],finish:{},start:{},direction:[-1,0],planning_area:[{},{},{}],sizes_confirmed:true,course_confirmed:true,derived_sections:[{}],attempt:{mode:'full',start_source:'live'},passages:[{kind:'gate',red:'dodge_gate_a_red',green:'dodge_gate_a_green'}]};
test('readiness explains stale starts and respects explicit offline planning',()=>{
 assert.ok(generationChecks(map,draft,false).every(check=>check.ready));
 assert.deepEqual(generationChecks(map,draft,true).filter(check=>!check.ready).map(c=>c.id),['start']);
 assert.ok(generationChecks(map,{...draft,attempt:{start_source:'manual'}},true).every(check=>check.ready));
});
test('default opening rejection and partial selection have distinct recovery steps',()=>{
 const checks=generationChecks(map,{...draft,clearance_m:2.1,preferred_buffer_m:2.1,attempt:{mode:'remaining',start_source:'manual',first_section:0,selection_confirmed:false}},false);
 assert.equal(checks.find(c=>c.id==='opening').step,2);
 assert.match(checks.find(c=>c.id==='opening').detail,/4.00 m.*4.20 m/);
 assert.equal(checks.find(c=>c.id==='remaining').ready,false);
 assert.equal(generationChecks(map,{...draft,attempt:{mode:'remaining',start_source:'manual',first_section:null,selection_confirmed:true}},false).find(c=>c.id==='remaining').ready,false);
});
test('review reasons cover approval, armed upload, stale link and acknowledgement',()=>{
 const args={draft,routeVisible:true,dirty:false,validation:{valid:true},approved:true,uploaded:false,stale:false,status:{armed:true,mode:4}};
 assert.match(reviewBlocks(args).upload,/Disarm/);
 assert.match(reviewBlocks(args).start,/wait for confirmation/);
 assert.match(reviewBlocks({...args,status:{armed:false,mode:4},stale:true}).upload,/Reconnect/);
 assert.equal(reviewBlocks({...args,status:{armed:false,mode:4},uploaded:true}).start,'');
 assert.match(reviewBlocks({...args,dirty:true,approved:false}).approve,/Save and validate/);
 assert.match(reviewBlocks({...args,routeVisible:false}).validate,/Generate/);
 assert.match(reviewBlocks({...args,status:{armed:false,mode:4},pending:{command:'upload'}}).upload,/readback/);
 assert.match(reviewBlocks({...args,uploaded:true,pending:{command:'start'}}).start,/awaiting confirmation/);
});
test('bad or missing telemetry ages never look fresh',()=>{
 const status={position:{latitude:40,longitude:-86},heartbeat_age_s:0,position_age_s:0};
 assert.equal(freshStatus(status,100),true);
 for(const value of [null,undefined,NaN,-1,4])assert.equal(freshStatus({...status,heartbeat_age_s:value},100),false);
 assert.equal(freshStatus(status,4000),false);assert.equal(freshStatus({...status,position:null},100),false);
});
test('structured API errors keep human reasons and identify useful recovery',()=>{
 assert.equal(errorText({errors:[{reason:'unsafe finish area'}]}),'unsafe finish area');
 assert.equal(explainFailure({detail:{errors:[{reason:'unsafe finish area'}]}}).title,'Finish area needs more room');
 assert.match(errorText([{loc:['body','speed'],msg:'positive value required'}]),/body → speed: positive value/);
 assert.match(explainFailure('Planning time limit reached').next,/does not prove/);
 assert.equal(explainFailure('Planning request time limit reached; no route was received.').title,'Planning response timed out');
 assert.match(explainFailure('boat request outcome unknown').next,/before retrying/);
});
test('configuration errors name an otherwise hidden task or individual tower',()=>{
 const settings=defaultSettings();settings.task_overrides.channel={speed_m_s:-1};
 assert.match(settingsError(settings),/Channel \/ Evade override/);
 settings.task_overrides={};settings.tower_avoidance.overrides.evade_detector_left={hard_m:2,soft_m:1};
 assert.match(settingsError(settings),/evade detector left/);
});

test('asynchronous failures and unknown outcomes stay distinct from request receipts',()=>{
 assert.equal(operationNotice({command:'upload',state:'pending'}),null);
 const unknown=operationNotice({command:'start',state:'unknown',detail:'boat restarted'});
 assert.equal(unknown.kind,'error');assert.match(unknown.title,/outcome unknown/);
 assert.match(unknown.next,/before retrying/);assert.equal(unknown.step,4);
 assert.match(operationNotice({command:'upload',state:'failed',detail:'mission readback mismatch'}).text,/readback mismatch/);
 assert.match(operationNotice({command:'upload',state:'succeeded'}).text,/readback succeeded.*separate action/);
});

test('running and completed missions do not prompt a second upload to start again',()=>{
 const args={draft,routeVisible:true,dirty:false,validation:{valid:true},approved:true,uploaded:false,stale:false,mission:'approved',status:{mission_id:'approved',state:'executing'}};
 assert.match(reviewBlocks(args).start,/already starting, running or stopping/);
 assert.match(reviewBlocks({...args,status:{mission_id:'approved',state:'complete'}}).start,/finished.*fresh attempt/);
});


test('a fresh identity mismatch blocks both execution actions without making missing telemetry a prerequisite',()=>{
 const args={draft,routeVisible:true,dirty:false,validation:{valid:true},approved:true,uploaded:true,stale:false,status:{armed:false,mode:4,identity_mismatch:true}};
 assert.match(reviewBlocks(args).upload,/identity mismatch/);assert.match(reviewBlocks(args).start,/identity mismatch/);
 assert.equal(reviewBlocks({...args,status:{armed:false,mode:4}}).upload,'');
 assert.equal(reviewBlocks({...args,status:{armed:false,mode:4}}).start,'');
});

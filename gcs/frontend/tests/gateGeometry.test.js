import test from 'node:test';
import assert from 'node:assert/strict';
import {replaceGateObject} from '../src/gateGeometry.js';
test('replacing a gate endpoint changes only the selected instance and revokes review and generated authority',()=>{
 const setup={course_confirmed:true,derived_sections:[{id:'gate'}],passages:[{id:'gate',kind:'gate',red:'a',green:'b'}]};
 const draft={steps:[{id:'one',setup},{id:'two',setup:structuredClone(setup)}],shared_crossings:[{}],waypoints:[{}],generation_identity:'approved'};
 const updated=replaceGateObject(draft,['two','gate','red'],{id:'c',type:'point'});
 assert.equal(updated.steps[0],draft.steps[0]);assert.equal(updated.steps[1].setup.passages[0].red,'c');assert.equal(draft.steps[1].setup.passages[0].red,'a');
 assert.equal(updated.steps[1].setup.course_confirmed,false);assert.deepEqual(updated.steps[1].setup.derived_sections,[]);
 assert.deepEqual(updated.shared_crossings,[]);assert.deepEqual(updated.waypoints,[]);assert.equal(updated.generation_identity,null);
 assert.throws(()=>replaceGateObject(draft,['two','gate','red'],{id:'b',type:'point'}),/two different/);
 assert.throws(()=>replaceGateObject(draft,['two','gate','red'],{id:'c',type:'point',object_type:'detector'}),/not a tower/);
 assert.throws(()=>replaceGateObject(draft,['gone','gate','red'],{id:'c',type:'point'}),/Select a gate/);
});

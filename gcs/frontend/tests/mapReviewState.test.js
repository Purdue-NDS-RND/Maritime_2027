import test from 'node:test';
import assert from 'node:assert/strict';
import {isNavigation,untypedNavigation,sameRoles,displayColour} from '../src/mapReviewState.js';

test('classification shortcut includes only untyped red/green points',()=>{
    const objects=[
        {id:'r',type:'point',category:'red',object_type:'unknown'},
        {id:'g',type:'cylinder',category:'green'},
        {id:'tower',type:'point',category:'red',object_type:'detector'},
        {id:'obstacle',type:'point',category:'green',object_type:'obstacle'},
        {id:'blue',type:'point',category:'blue',object_type:'unknown'},
        {id:'polygon',type:'polygon',category:'red',object_type:'unknown'},
        {id:'typed',type:'point',category:'red',object_type:'buoy'}
    ];
    assert.deepEqual(untypedNavigation(objects).map(o=>o.id),['r','g']);
    assert.deepEqual(objects.filter(isNavigation).map(o=>o.id),['typed']);
});

test('confirmation belongs to exact roles, independent of property order',()=>{
    assert.ok(sameRoles({red:'a',green:'b'},{green:'b',red:'a'}));
    assert.ok(!sameRoles({red:'a',green:'b'},{red:'c',green:'b'}));
    assert.ok(!sameRoles({red:'a'},{red:'a',green:'b'}));
    assert.ok(!sameRoles(undefined,undefined));
});

test('unknown type overrides observed color without changing classification',()=>{
    for(const category of ['red','green','zebra','purple']) {
        const object={object_type:'unknown',category};
        assert.equal(displayColour(object,'#e74b50'),'#999');
        assert.equal(object.category,category);
    }
    assert.equal(displayColour({category:'red'},'#e74b50'),'#999');
    assert.equal(displayColour({object_type:'buoy',category:'red'},'#e74b50'),'#e74b50');
    assert.equal(displayColour({object_type:'detector'},'#bd79e4'),'#bd79e4');
});

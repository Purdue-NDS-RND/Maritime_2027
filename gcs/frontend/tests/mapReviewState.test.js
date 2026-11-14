import test from 'node:test';
import assert from 'node:assert/strict';
import {isNavigation,untypedNavigation,sameRoles} from '../src/mapReviewState.js';

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
